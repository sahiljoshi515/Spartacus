"""Day 4 -- sub-agents: delegation as a tool, and the depth limit that saves you.

Concept this file teaches: a sub-agent is not new machinery. It is the harness
you already have, constructed again with an empty message list, exposed to the
model as one more tool. The parent hands over a task and gets back a paragraph;
the hundred turns of reading, grepping and false starts that produced the
paragraph happen in a context the parent never pays for and never sees. That is
the entire value, and it is also the entire risk -- the parent cannot check the
child's work, only its report.

Design rules this file embodies:
  * The child is built lazily, by a callback, not passed in. A ``Harness`` that
    constructed its children eagerly would recurse forever at import time; a
    ``make_harness`` closure only runs when the model actually delegates.
  * Depth is counted and capped. An agent that can spawn agents will, given a
    vague enough task, spawn them all the way down -- so the limit is a
    constructor argument rather than good intentions, and hitting it returns a
    sentence telling the model to do the work itself.
  * The refusal is a tool result, not an exception, exactly like ``security.py``
    and every tool in ``tools.py``. The model reads it and adapts.
  * The description is written for the caller that keeps getting this wrong.
    A model that thinks the child can see the conversation will delegate
    "finish that file", and the child, with no idea which file, will invent one.
"""

from .tools import tool

DESCRIPTION = ("Delegate a self-contained task to a fresh sub-agent with its own "
               "clean context. The sub-agent CANNOT see this conversation, so the "
               "task must carry every detail it needs -- file names, contents, "
               "requirements -- stated in full. Returns the sub-agent's final "
               "report, which is all you will ever see of its work.")

LIMIT = "ERROR: sub-agent depth limit reached; do this task yourself"


def subagent_tool(make_harness, depth=0, max_depth=2):
    """Return the ``spawn_agent`` tool, bound to this agent's place in the tree."""
    @tool(DESCRIPTION,
          task="The complete, self-contained task for the sub-agent, including "
               "every file name, requirement and detail it needs to work alone")
    def spawn_agent(task):
        """Run ``task`` in a child harness and return its final report."""
        if depth >= max_depth:
            # Refuse before building anything: the cheapest recursion to stop is
            # the one that never allocated a child in the first place.
            return LIMIT
        child = make_harness(depth + 1)
        return child.run(task)

    return spawn_agent
