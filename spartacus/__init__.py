"""Spartacus -- a small, sharp coding agent, built one day at a time.

The package is deliberately readable end to end. In dependency order:

    provider.py   the only file that knows the wire
    loop.py       think, act, observe, repeat
    tools.py      a capability in two halves: the spec and the code
    security.py   yes, no, or ask a human
    context.py    fitting an unbounded task into a bounded window
    memory.py     the part of the agent that outlives the conversation
    skills.py     instructions loaded only when they are needed
    session.py    the transcript on disk, and repair when it is torn
    subagent.py   delegation as a tool
    harness.py    the one object that wires all of the above together
    fleet.py      many harnesses at once, one directory each
    cli.py        the front door: headless and interactive

Five names are exported, because five is what a caller needs: the harness to
run, the policy to constrain it, the pair used to write a tool of your own, and
the fleet runner for when one agent is not enough.
"""

from .fleet import run_fleet
from .harness import Harness
from .security import Policy
from .tools import Tool, tool

__all__ = ["Harness", "Policy", "Tool", "run_fleet", "tool"]
