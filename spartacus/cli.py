"""Day 4 -- the entry point, reserved. Day 5 turns this into the real command line.

Concept this file teaches: ``python3 -m spartacus`` should exist from the moment
the package can do anything, even when all it can do is say what comes next. The
stub is here so that day 5 rewrites one function instead of inventing a module,
and so ``__main__.py`` never needs to know more than a name to call.
"""

USAGE = """spartacus -- a small, sharp coding agent.

The command line arrives on day 5. Today the harness is the API:

    from spartacus import Harness

    agent = Harness(workdir=".")
    agent.resume()                      # continue the newest session, if any
    print(agent.run("your task here"))
"""


def main(argv=None):
    """Print the usage notice and exit cleanly. Day 5 replaces this wholesale."""
    print(USAGE)
    return 0
