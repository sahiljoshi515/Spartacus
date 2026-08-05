"""Day 1 demo -- one hand-written tool, wired to the loop by hand.

Concept this file teaches: the entire contract a Spartacus tool must satisfy is
two attributes -- a ``.spec`` the provider can ship to the model and a ``.run``
the loop can call with keyword arguments. Day 2 generates both from a
decorator; today they are typed out so there is no magic left to guess at.

Design rules this file embodies:
  * The demo supplies its own policy: ``on_event`` prints the transcript,
    ``before_tool`` allows everything. Day 2 tightens the second one.
  * ``count`` is declared as a string because the model returns whatever JSON
    scalar it feels like; the tool coerces at the boundary rather than trusting
    the caller. Tools validate their own arguments.

Run from the repo root:  python3 demos/day1_dice.py ["some other task"]
"""

import pathlib
import random
import sys

# Demos live one level below the package, so put the repo root on the path
# before importing it. Day 4's `python3 -m spartacus` needs no such help.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from spartacus import loop, provider  # noqa: E402  (must follow the path fix)

SYSTEM = "You are Spartacus, a concise assistant. Use tools when they help."
TASK = "Roll 3 dice and tell me whether the total beats 10"


class RollDice:
    """The minimum viable tool: a spec the model reads, a run the loop calls."""

    spec = {"schema": {
        "name": "roll_dice",
        "description": "Roll count six-sided dice",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "string", "description": "How many dice"},
            },
            "required": ["count"],
        },
    }}

    def run(self, count):
        """Roll ``count`` six-sided dice and return the individual results."""
        return [random.randint(1, 6) for _ in range(int(count))]


def on_event(kind, payload):
    """Print the transcript as it happens: replies, calls, and results."""
    if kind == "assistant":
        if payload["text"]:
            print("\n[assistant] %s" % payload["text"])
        for call in payload["tool_calls"]:
            print("[assistant] calls %s(%s)" % (call["name"], call["args"]))
    elif kind == "tool_start":
        print("[tool_start] %s" % payload["name"])
    elif kind == "tool_end":
        print("[tool_end]   %s" % payload["result"])


def allow_everything(call):
    """The day 1 permission gate: return None, meaning every call is allowed."""
    return None


def main():
    """Run one task through the loop with a single dice tool available."""
    task = sys.argv[1] if len(sys.argv) > 1 else TASK
    messages = [{"role": "user", "text": task}]
    print("[user] %s" % task)
    answer = loop.run_loop(provider.DEFAULT_MODEL, SYSTEM, messages,
                           {"roll_dice": RollDice()}, on_event, allow_everything)
    print("\n[final] %s" % answer)


if __name__ == "__main__":
    main()
