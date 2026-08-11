"""Day 4 demo -- the spine: a run that survives being killed, and work handed down.

Concept this file teaches: days 1 to 3 were wired together by hand in every
demo -- build the toolset, assemble the prompt, pick a policy, pass six
arguments to ``run_loop``. Today that is one line, because ``Harness`` does the
wiring. What the demos gain from it is the thing you cannot fake by hand: the
transcript is on disk as it happens, so a process that dies is a process that
can be continued.

The scenes:
  * ``start [n]`` -- begin the file task. With ``n``, SIGKILL this process the
    instant the model asks for its n-th tool, which is the one moment that
    actually needs repairing: the call is written down, the result never will
    be. Without ``n``, run normally so you can kill it from another terminal.
  * ``resume`` -- a new process over the same directory. ``resume()`` reads the
    log, invents a result for the call the crash orphaned, and the run carries
    on from there.
  * ``subagents`` -- delegate two files to two children, then verify their work
    in the parent, and count the session logs left behind.

Design rules this file embodies:
  * The kill is fault injection, and says so. Sending yourself SIGKILL is a real
    ``kill -9`` -- no handlers, no flush, no cleanup -- but timing it by hand
    would be hopeless, because the window between "call recorded" and "result
    recorded" is microseconds wide. Deterministic beats realistic when the
    point is to show the mechanism.
  * Children print through the parent's ``on_event``, so a sub-agent's turns
    appear nested between ``spawn_agent``'s start and end. Delegation you
    cannot watch is delegation you cannot debug.

Run from the repo root:
    python3 demos/day4_spine.py start 3
    python3 demos/day4_spine.py resume
    python3 demos/day4_spine.py subagents
"""

import os
import pathlib
import shutil
import signal
import sys

# Demos live one level below the package, so put the repo root on the path
# before importing it. ``python3 -m spartacus`` needs no such help.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from spartacus import Harness, session  # noqa: E402  (must follow the path fix)

SCRATCH = pathlib.Path(__file__).resolve().parent.parent / "scratch"
CLIP = 400  # characters of a tool result worth putting on screen

FILE_TASK = ("Create part1.txt through part5.txt one at a time, then SUMMARY.md "
             "describing each")
DELEGATE_TASK = ("Use spawn_agent twice: delegate writing utils.py with a "
                 "slugify(text) function to one child, and test_utils.py with "
                 "five asserts to another; then run python3 test_utils.py "
                 "yourself and report")


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


def workspace(name, fresh=False):
    """Return ``scratch/<name>``, emptied first when a scene needs a clean start."""
    path = SCRATCH / name
    if fresh and path.exists():
        shutil.rmtree(path)  # scratch/ is the demo's own ground, and git ignores it
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs(workdir):
    """Return the session log filenames in ``workdir``, sorted."""
    base = workdir / session.SESSION_DIR
    return sorted(p.name for p in base.iterdir()) if base.is_dir() else []


def scene_start():
    """Begin the file task, optionally dying mid-tool to leave a call unanswered."""
    workdir = workspace("day4_resume", fresh=True)
    kill_at = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    state = {"calls": 0}

    def watch(kind, payload):
        """Print like normal, and pull the plug at the chosen tool call."""
        on_event(kind, payload)
        if kind != "tool_start":
            return
        state["calls"] += 1
        if kill_at and state["calls"] == kill_at:
            # The assistant message carrying this call is already on disk; its
            # result never will be. That is precisely the state session.repair
            # exists to fix, and the only way to reach it reliably is to stop
            # the process here, between the two writes.
            print("\n[crash] SIGKILL at tool call %d -- the call is recorded, "
                  "the result is not" % kill_at)
            sys.stdout.flush()
            os.kill(os.getpid(), signal.SIGKILL)

    print("[workdir] %s\n[user] %s" % (workdir, FILE_TASK))
    agent = Harness(workdir, on_event=watch)
    print("\n[final] %s" % agent.run(FILE_TASK))
    print("\n[sessions] %s\n[on disk] %s"
          % (logs(workdir), sorted(p.name for p in workdir.iterdir())))


def scene_resume():
    """Pick the killed run up in a new process and carry it to the end."""
    workdir = workspace("day4_resume")
    agent = Harness(workdir, on_event=on_event)
    resumed = agent.resume()
    print("[workdir] %s\n[resume] %s -- %d messages from %s"
          % (workdir, resumed, len(agent.messages),
             os.path.basename(agent.session_path or "")))
    for message in agent.messages:
        if message.get("text") == session.INTERRUPTED:
            print("[repair] %s: %s" % (message["name"], message["text"]))
    print("\n[final] %s" % agent.run("continue the task"))
    print("\n[sessions] %s\n[on disk] %s"
          % (logs(workdir), sorted(p.name for p in workdir.iterdir())))


def scene_subagents():
    """Delegate two files to two children, then check their work in the parent."""
    workdir = workspace("day4_agents", fresh=True)
    print("[workdir] %s\n[user] %s" % (workdir, DELEGATE_TASK))
    agent = Harness(workdir, on_event=on_event)
    print("\n[final] %s" % agent.run(DELEGATE_TASK))
    # One log, not three: the children ran with persist=False, so the newest
    # session in this directory is still the parent's.
    print("\n[sessions] %s\n[on disk] %s"
          % (logs(workdir), sorted(p.name for p in workdir.iterdir())))


SCENES = {"start": scene_start, "resume": scene_resume, "subagents": scene_subagents}


def main():
    """Run one named scene, defaulting to the interrupted file task."""
    name = sys.argv[1] if len(sys.argv) > 1 else "start"
    if name not in SCENES:
        sys.exit("usage: day4_spine.py [%s] [kill-at]" % "|".join(SCENES))
    SCENES[name]()


if __name__ == "__main__":
    main()
