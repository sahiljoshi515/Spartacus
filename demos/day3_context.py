"""Day 3 demo -- the same loop again, now with a past it can afford to keep.

Concept this file teaches: three files landed today and the loop did not change
by a line. Compaction goes into ``before_turn``, the socket day 1 left empty;
memory and skills go into the system prompt, which was always just a string the
caller built. Everything new is an argument.

The scenes, each proving one claim:
  * ``compaction`` -- a task too long for a 1,500-token budget finishes anyway,
    and you can watch the history collapse mid-run.
  * ``memory`` -- the agent writes a fact down, then a second conversation that
    starts from an empty message list answers a question about it.
  * ``recall`` -- the same question in a *new process*, with no tools at all, so
    a right answer cannot have come from anywhere but the system prompt.
  * ``skills`` -- one writing task, run twice, against two directories that
    differ by a single markdown file. The voice changes; no code does.

Design rules this file embodies:
  * Each scene gets its own workspace under ``scratch/``. Two scenes sharing a
    directory would share a memory file, and the recall proof would be a lie.
  * ``before_turn`` here is a wrapper, not a rewrite: it calls ``compact`` and
    reports what happened. Compaction that fires silently is compaction you
    cannot debug, but the printing is the demo's job, never the engine's.
  * The brand-voice skill is written out below as a plain string. That is the
    point of the scene -- the entire behaviour change is text on disk, so it
    belongs somewhere you can read it, not in a fixture you have to go find.

Run from the repo root:  python3 demos/day3_context.py [scene]
"""

import pathlib
import shutil
import sys

# Demos live one level below the package, so put the repo root on the path
# before importing it. Day 4's `python3 -m spartacus` needs no such help.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from spartacus import (context, loop, memory, provider,  # noqa: E402  (after path fix)
                       security, skills, tools)

SCRATCH = pathlib.Path(__file__).resolve().parent.parent / "scratch"
BUDGET = 1500   # tokens of history tolerated before the old half is summarised
CLIP = 600      # characters of a tool result worth putting on screen

PING_TASK = ("Create five files one.txt through five.txt, each with 20 lines of "
             "the word ping, one write_file at a time with a read back after "
             "each; then MANIFEST.md listing each file and its line count "
             "verified with wc -l")
FACT_TASK = ("Remember for future sessions: this project deploys to fly.io in "
             "the iad region, and we never deploy on a Friday.")
QUESTION = "Where does this project deploy, in which region, and when must we not?"
WRITE_TASK = ("Write blurb.txt: three sentences announcing that our CLI now "
              "works offline.")

BRAND_VOICE_SKILL = """---
name: brand-voice
description: The mandatory voice for any user-facing prose this project ships. \
Load it before writing a single sentence.
---

# Brand voice

Every user-facing sentence this project ships is written the way a pirate
speaks. This is not a joke and it is not optional.

- Open with "Ahoy!".
- Address the reader as "ye" or "matey", never as "you".
- Use "be" where a landlubber writes "is" or "are": "the CLI be ready".
- Reach for the nautical word when one fits: the network is "the open sea",
  working offline is "sailin' dark".
- Close with "Fair winds."
- Keep it short. A pirate does not pad.
"""


def on_event(kind, payload):
    """Print the transcript as it happens: replies, calls, and clipped results."""
    if kind == "assistant":
        if payload["text"]:
            print("\n[assistant] %s" % payload["text"])
        for call in payload["tool_calls"]:
            print("[assistant] calls %s(%s)" % (call["name"], _short(call["args"])))
    elif kind == "tool_start":
        print("[tool_start] %s" % payload["name"])
    elif kind == "tool_end":
        print("[tool_end]   %s" % _short(payload["result"]))


def _short(value):
    """Render ``value`` for the terminal, clipped, on one line per newline kept."""
    text = str(value)
    return text if len(text) <= CLIP else "%s … (+%d chars)" % (text[:CLIP],
                                                                len(text) - CLIP)


def show(path, label):
    """Print a file the agent was meant to produce, or say plainly it is missing.

    A demo that dies of ``FileNotFoundError`` reports nothing about the run
    that led there; a demo that prints "(missing)" has just told you the result.
    """
    print("\n[%s]\n%s" % (label, path.read_text() if path.exists() else "(missing)"))


def workspace(name, fresh=False):
    """Return ``scratch/<name>``, emptied first when a scene needs a clean start."""
    path = SCRATCH / name
    if fresh and path.exists():
        shutil.rmtree(path)  # scratch/ is the demo's own ground, and git ignores it
    path.mkdir(parents=True, exist_ok=True)
    return path


def session(workdir):
    """Return the ``(system, toolset)`` pair for a session over ``workdir``.

    This is the whole of day 3 as a caller sees it: the prompt is assembled
    from disk -- base instructions, memory, skill catalogue -- and two tools
    are added so the agent can reach the same two files itself.
    """
    @tools.tool("Load a skill's full instructions, then follow them",
                name="Skill name, exactly as listed in your system prompt")
    def use_skill(name):
        return skills.read_skill(workdir, name)

    @tools.tool("Save a durable fact about this project for every future session",
                note="One short sentence worth remembering")
    def remember(note):
        return memory.remember(workdir, note)

    toolset = tools.core_tools(workdir) + [use_skill, remember]
    system = memory.build_system_prompt(workdir, skills.catalog_prompt(workdir))
    return system, {tool.name: tool for tool in toolset}


def run(workdir, task, system=None, toolset=None, before_turn=None):
    """Run one conversation from an empty history and return the final text."""
    built_system, built_tools = session(workdir)
    messages = [{"role": "user", "text": task}]
    print("\n[workdir] %s\n[user] %s" % (workdir, task))
    answer = loop.run_loop(provider.DEFAULT_MODEL,
                           built_system if system is None else system, messages,
                           built_tools if toolset is None else toolset,
                           on_event, security.Policy("yolo").check,
                           before_turn=before_turn)
    print("\n[final] %s" % answer)
    return answer


def scene_compaction():
    """A task longer than its budget: watch the history collapse and finish anyway."""
    workdir = workspace("day3_pings", fresh=True)

    def before_turn(messages):
        """The socket day 1 left empty: compact, and say so when it happens."""
        before = context.estimate_tokens(messages)
        kept = context.compact(provider.DEFAULT_MODEL, messages, BUDGET)
        # `is not` and not a length test: compact hands back the very same list
        # when it did nothing, which is how a caller tells a no-op from a cut.
        if kept is not messages:
            print("\n[compact] %d messages / ~%d tokens -> %d messages / ~%d tokens"
                  % (len(messages), before, len(kept), context.estimate_tokens(kept)))
        return kept

    print("[budget] %d tokens of history" % BUDGET)
    run(workdir, PING_TASK, before_turn=before_turn)
    print("\n[on disk] %s" % sorted(p.name for p in workdir.iterdir()))


def scene_memory():
    """Write a fact in one conversation; answer from it in the next."""
    workdir = workspace("day3_project", fresh=True)
    run(workdir, FACT_TASK)
    show(workdir / memory.MEMORY_FILE, memory.MEMORY_FILE)
    print("\n=== a completely fresh conversation over the same directory ===")
    scene_recall()


def scene_recall():
    """Ask about the remembered fact with no history and, deliberately, no tools."""
    workdir = workspace("day3_project")
    system = memory.build_system_prompt(workdir)
    print("\n=== system prompt, rebuilt from disk ===\n%s\n===" % system)
    # An empty toolset is the proof. The agent cannot read the memory file, so
    # a correct answer can only have come from the prompt it was born with.
    run(workdir, QUESTION, system=system, toolset={})


def scene_skills():
    """The same writing task in two directories, one markdown file apart."""
    for name, skill in (("day3_plain", None), ("day3_brand", BRAND_VOICE_SKILL)):
        workdir = workspace(name, fresh=True)
        if skill:
            path = workdir / skills.SKILLS_DIR / "brand-voice" / skills.SKILL_FILE
            path.parent.mkdir(parents=True)
            path.write_text(skill)
        print("\n=== %s ===\n[catalogue] %r"
              % (name, skills.catalog_prompt(workdir)))
        run(workdir, WRITE_TASK)
        show(workdir / "blurb.txt", "blurb.txt")


SCENES = {"compaction": scene_compaction, "memory": scene_memory,
          "recall": scene_recall, "skills": scene_skills}


def main():
    """Run one named scene, defaulting to compaction."""
    name = sys.argv[1] if len(sys.argv) > 1 else "compaction"
    if name not in SCENES:
        sys.exit("usage: day3_context.py [%s]" % "|".join(SCENES))
    SCENES[name]()


if __name__ == "__main__":
    main()
