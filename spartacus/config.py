"""Configuration: one file of keys, outside the repo, read only when needed.

Concept this file teaches: an API key has exactly two bad homes -- a shell
profile, where it is exported to every process on the machine, and a file
inside the repository, where it is one ``git add -A`` from being public. This
is the third home: a single ``KEY=value`` file under ``~/.config``, owned by
the user, read by the harness when it needs a credential and at no other time.

Design rules this file embodies:
  * The real environment always wins. A file that overrode ``$OPENAI_API_KEY``
    would silently ignore the key you just exported to test something, which is
    the most confusing bug a config loader can have.
  * Loading is lazy and idempotent. Nothing is read at import -- importing a
    library must not touch your disk -- and the file is parsed once, at the
    moment a key is first wanted.
  * The parser is deliberately dumb: ``KEY=value``, one per line, ``#`` for
    comments, optional ``export``. It is not a shell, and a config file that
    needs a shell to interpret it is a config file that can run code.
"""

import os

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "spartacus", "env")

_loaded = False


def load(path=None, override=False):
    """Read ``KEY=value`` lines into the environment; return the names it set.

    Absent file, unreadable file and malformed line are all non-events: the
    harness must still start, and the missing-key error it raises later says
    far more than a parse error here would.
    """
    global _loaded
    target = path or CONFIG_PATH
    if path is None:
        if _loaded:
            return []
        _loaded = True  # set before reading: one attempt, success or not
    if not os.path.isfile(target):
        return []
    applied = []
    with open(target, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            pair = _parse(line)
            if pair and (override or not os.environ.get(pair[0])):
                os.environ[pair[0]] = pair[1]
                applied.append(pair[0])
    return applied


def _parse(line):
    """Return ``(name, value)`` for one config line, or ``None`` if it is not one."""
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("export "):
        line = line[len("export "):]
    name, _, value = line.partition("=")
    name, value = name.strip(), value.strip()
    if not name:
        return None
    # Strip one matched pair of quotes, the way people actually write these.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return name, value


def describe(path=None):
    """Return a human-readable line about the config file, for the CLI banner."""
    target = path or CONFIG_PATH
    if not os.path.isfile(target):
        return "%s (not present)" % target
    mode = oct(os.stat(target).st_mode & 0o777)[2:]
    warn = "" if mode == "600" else "  [warning: mode %s, consider chmod 600]" % mode
    return "%s%s" % (target, warn)
