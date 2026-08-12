"""Day 5 demo -- the proof: three real products, built by the harness itself.

Concept this file teaches: everything before today was the harness proving it
works on toy tasks. This is the harness doing a job. Three unrelated projects
are built concurrently, each in its own directory, each by an agent that reads
the same design skill off disk and holds itself to it -- and then each is put
through a second pass in the *same session*, told to review its own work as a
demanding director and fix what it finds.

That second pass is the interesting half. A single-shot agent stops at "it
works"; the review turn is what moves output from a demo to something you would
show someone. It costs one more `run` on a harness that still remembers
everything it did, which is exactly what day 4's session was for.

Design rules this file embodies:
  * The skill is written before any harness is built. ``Harness`` decides
    whether to offer ``use_skill`` at construction time, so a skill that lands
    afterwards is a skill the agent is never told about.
  * One directory per project, and the harness cache is keyed by it. Phase two
    must reuse the *same* object, or "review what you produced" arrives at an
    agent with no memory of producing anything.
  * Output is prefixed and clipped. Three agents writing to one terminal is
    unreadable otherwise, and the full transcript is on disk anyway.

Run from the repo root:
    python3 demos/day5_fleet.py [build|review|both] [project ...]
"""

import json
import os
import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from spartacus import Harness, run_fleet  # noqa: E402  (must follow the path fix)
from spartacus.skills import SKILL_FILE, SKILLS_DIR  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent / "projects"
MODEL = os.environ.get("SPARTACUS_MODEL", "gemini-3.6-flash")
WORKERS = 3
MAX_TURNS = 120
CLIP = 110

SKILL = """---
name: design-engineering
description: The quality bar every page and program here must clear. Load it \
before writing a single file, and again before you claim to be finished.
---

# Design engineering

Work is not finished when it runs. It is finished when it clears every line
below. Hold yourself to these as hard minimums, not as aspirations.

- A real design system, expressed as CSS custom properties: colour, type scale,
  spacing scale, radius, shadow. No magic numbers scattered through the rules.
- At least 9 distinct sections for a landing page.
- At least 1,200 words of real copy. No lorem ipsum, no placeholder text, no
  "description goes here". Write the actual words a real company would ship.
- At least 4 hand-drawn inline SVG illustrations, one of which is a product
  artifact in the hero. Hand-drawn means paths you author, not an icon font and
  not an external image.
- At least 3 working interactive behaviors, wired in real JavaScript.
- Responsive at 360, 768, and 1280 pixels wide.
- Semantic HTML with visible focus states for every interactive element.
- A self-review pass before you finish, which counts the sections, the words,
  the SVGs, and the interactions against these minimums and fixes any
  shortfall you find.
"""

REVIEW = ("Review every file you produced against the skill bar as a demanding "
          "design director; list 12 concrete deficiencies; fix them all; "
          "verify again.")

PROJECTS = [
    {"name": "artisan-coffee", "task": (
        "Build a self-contained index.html for a specialty coffee roaster in "
        "Goa. It must have: a sticky nav; a hero containing a hand-drawn inline "
        "SVG product artifact; six origin cards each with a price; a three-tier "
        "subscription table with a working monthly/annual toggle that changes "
        "the displayed prices; brew-guide tabs that switch panels; an FAQ "
        "accordion that expands and collapses; and a dark-mode toggle whose "
        "choice persists in localStorage. Everything inline in the one file: no "
        "external CSS, JS, images or fonts. Load the design-engineering skill "
        "first and meet every minimum in it.")},
    {"name": "taskman", "task": (
        "Build a Python command-line task manager. taskman.py uses argparse "
        "with subcommands add, list, done, rm and stats; it persists tasks as "
        "JSON; and list prints an aligned table. Also write test_taskman.py: a "
        "unittest suite of at least 10 cases that drives taskman.py via "
        "subprocess against a temporary store directory, never the real one. "
        "Run python3 -m unittest test_taskman.py -v yourself and do not stop "
        "until every test passes. Also write README.md documenting every "
        "subcommand with examples.")},
    {"name": "viper", "task": (
        "Build a canvas snake game as a single self-contained index.html. Grid "
        "movement driven by requestAnimationFrame; food that spawns clear of "
        "the snake; the snake speeds up every 5 foods eaten; a live score; "
        "pause and resume; restart; and a high score kept in localStorage. "
        "Arrow keys and WASD both steer, and the snake may not reverse into "
        "itself. Everything inline in the one file. Load the design-engineering "
        "skill first and give the page a real designed shell around the "
        "canvas, not a bare element.")},
]

TURNS = {}
_LOCK = threading.Lock()
_AGENTS = {}


def printer(name):
    """Return an ``on_event`` that prefixes every line with the project name."""
    def show(kind, payload):
        if kind == "assistant":
            with _LOCK:
                TURNS[name] = TURNS.get(name, 0) + 1
            if payload["text"]:
                print("[%s] %s" % (name, _clip(payload["text"].strip())))
            for call in payload["tool_calls"]:
                print("[%s]   %s %s" % (name, call["name"],
                                        _clip(_arguments(call["args"]))))
        elif kind == "tool_end":
            print("[%s]   -> %s" % (name, _clip(_first_line(payload["result"]))))
        sys.stdout.flush()  # three threads share this pipe; buffering interleaves badly
    return show


def _arguments(args):
    """Render a call's arguments as one flat line."""
    return " ".join("%s=%s" % (k, str(v).replace("\n", "\\n")) for k, v in args.items())


def _first_line(result):
    """Return the first non-empty line of a tool result, or a stand-in."""
    for line in str(result).splitlines():
        if line.strip():
            return line.strip()
    return "(no output)"


def _clip(text, limit=CLIP):
    """Shorten ``text`` to ``limit`` characters, marking what was cut."""
    text = " ".join(text.split())
    return text if len(text) <= limit else "%s… (+%d)" % (text[:limit], len(text) - limit)


def make_harness(workdir):
    """Return this project's harness, building it once and reusing it after.

    The cache is the whole point: phase two runs on the same object, so the
    agent reviewing the work is the agent that did it, with the transcript to
    prove it. A fresh harness would be told to review files it had never seen.
    """
    key = str(workdir)
    with _LOCK:
        if key not in _AGENTS:
            _AGENTS[key] = Harness(workdir, model=MODEL, max_turns=MAX_TURNS,
                                   on_event=printer(os.path.basename(key)))
        return _AGENTS[key]


def prepare(project):
    """Create the project directory and plant the skill the agent will load."""
    workdir = ROOT / project["name"]
    skill = workdir / SKILLS_DIR / "design-engineering" / SKILL_FILE
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(SKILL, encoding="utf-8")
    return workdir


def main():
    """Build, review, or both, for all projects or the ones named on the line."""
    phase = sys.argv[1] if len(sys.argv) > 1 else "both"
    if phase not in ("build", "review", "both"):
        sys.exit("usage: day5_fleet.py [build|review|both] [project ...]")
    wanted = sys.argv[2:] or [p["name"] for p in PROJECTS]
    chosen = [p for p in PROJECTS if p["name"] in wanted]

    jobs = [{"name": p["name"], "workdir": str(prepare(p)), "task": p["task"]}
            for p in chosen]
    print("[fleet] model=%s workers=%d projects=%s"
          % (MODEL, WORKERS, [j["name"] for j in jobs]))

    results = {}
    if phase in ("build", "both"):
        print("\n=== phase 1: build ===")
        for r in run_fleet(jobs, make_harness, max_workers=WORKERS):
            results[r["name"]] = r
    if phase in ("review", "both"):
        print("\n=== phase 2: review ===")
        review = [dict(job, task=REVIEW) for job in jobs]
        for r in run_fleet(review, make_harness, max_workers=WORKERS):
            results[r["name"]] = r

    print("\n=== fleet result ===")
    for name in [j["name"] for j in jobs]:
        r = results.get(name, {})
        print("%-16s ok=%-5s turns=%-4s %s"
              % (name, r.get("ok"), TURNS.get(name, 0), _clip(str(r.get("report", "")))))
    (ROOT / "fleet-report.json").write_text(
        json.dumps({"results": results, "turns": TURNS}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
