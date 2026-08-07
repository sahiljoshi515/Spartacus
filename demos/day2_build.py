"""Day 2 demo -- the same loop as yesterday, now able to touch a real machine.

Concept this file teaches: nothing in the loop changed. Day 1 wired one
hand-written tool through ``before_tool=allow_everything``; today the same call
gets six generated tools and a real policy, and the difference in what the agent
can do is entirely in the two objects passed in. That is what the sockets were
for.

Design rules this file embodies:
  * The agent gets a scratch directory, not the repo. ``core_tools`` confines
    every path to what it is handed, so choosing that directory is the single
    most consequential line in this file -- for the five file tools. ``bash``
    gets a shell, and a shell goes where it likes; see ``security.py``.
  * The policy is ``yolo`` -- and "yolo" still blocks the deny list. Run the
    delete-my-home task below and watch a mode named after recklessness refuse.
  * Display stays in ``on_event``, including the clipping: a 4,000-line read is
    a fine tool result and a terrible terminal.

Run from the repo root:  python3 demos/day2_build.py ["some other task"]
"""

import pathlib
import sys

# Demos live one level below the package, so put the repo root on the path
# before importing it. Day 4's `python3 -m spartacus` needs no such help.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from spartacus import loop, provider, security, tools  # noqa: E402  (after path fix)

WORKDIR = pathlib.Path(__file__).resolve().parent.parent / "scratch"
SYSTEM = ("You are Spartacus, a concise coding agent. You work inside %s, and "
          "the file tools cannot reach outside it. Keep your work there. "
          "Use the tools to do the work rather than "
          "describing it, and verify with bash before you report a result: "
          "never state an output you have not actually seen. If a tool refuses, "
          "read the reason and adapt -- do not retry the same call.")
TASK = ("Create fib.py with an iterative fib(n), a __main__ printing fib(30), "
        "run it and confirm the output is 832040")
CLIP = 600  # characters of a tool result worth putting on screen


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


def main():
    """Run one task against the scratch directory with the full tool set."""
    task = sys.argv[1] if len(sys.argv) > 1 else TASK
    WORKDIR.mkdir(exist_ok=True)
    policy = security.Policy("yolo")
    toolset = {t.name: t for t in tools.core_tools(WORKDIR)}
    messages = [{"role": "user", "text": task}]
    print("[workdir] %s\n[policy] %s\n[user] %s" % (WORKDIR, policy.mode, task))
    answer = loop.run_loop(provider.DEFAULT_MODEL, SYSTEM % WORKDIR, messages,
                           toolset, on_event, policy.check)
    print("\n[final] %s" % answer)


if __name__ == "__main__":
    main()
