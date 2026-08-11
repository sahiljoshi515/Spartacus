"""Day 4 -- ``python3 -m spartacus``: one line, so the entry point can move.

Concept this file teaches: a ``__main__`` that contains logic is logic nobody
can import and nobody can test. This one resolves a name and forwards an exit
code; everything it appears to do lives in ``cli.py``.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
