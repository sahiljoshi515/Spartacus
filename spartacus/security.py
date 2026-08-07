"""Day 2 -- the gate: one function that answers yes, no, or ask a human.

Concept this file teaches: capability and permission are separate questions
answered by separate files. ``tools.py`` decides what is *possible*; this decides
what is *allowed*, and it plugs straight into the ``before_tool`` socket the loop
has been holding open since day 1. Neither file imports the other, which is the
point: you can read the whole permission story of this harness in one screen.

Design rules this file embodies:
  * The deny list runs before the modes, including yolo. A mode says how much
    the human wants to be asked; the deny list says what nobody gets to do by
    accident, however trusting the mode.
  * ``check`` returns a *reason*, not ``False``. The loop turns it into
    "BLOCKED: <reason>" and hands it to the model as a tool result, so the model
    reads why and changes plan. A gate that only says no teaches it to retry.
  * Refusing is the default. An approver of ``None`` means nobody is attached to
    answer, and safe mode with nobody attached must be safe, not permissive.
  * Read-only is a real mode, not a debugging aid: it is what you give an agent
    pointed at a repository you do not own.

Honest about its limits, because this is the file people trust by mistake. A
deny list of regexes over a shell command is a speed bump, not a sandbox:
``rm -rf ~`` has a hundred spellings -- a variable, a base64 pipe, a Python
one-liner -- and this catches the ones people type. More important, ``resolve``
in ``tools.py`` confines the five *file* tools and nothing else: ``bash`` gets a
shell, and ``cat ../../etc/passwd`` is not a path the harness ever inspects. So
``bash`` is the hole, by construction, and the only real boundaries around it
are the account this process runs as and an OS sandbox this harness does not yet
build. Read the list as "catch the fat-finger", never as "the tool is safe now".
"""

import re

MODES = ("read-only", "safe", "yolo")

# Tools that cannot change anything, so they never need a human in the way.
READ_TOOLS = {"read_file", "list_files", "grep"}

DENY_PATTERNS = [
    # The trailing class is load-bearing: without "*" this misses "rm -rf /*",
    # which is the spelling people actually type. "/tmp/x" is left alone.
    r"rm\s+(-\S+\s+)*['\"]?(/|~|\$HOME)['\"]?(\s|$|[/*])",  # rm at a home or root
    r"\bsudo\b",                                         # privilege escalation
    r"\bmkfs\b|\bdd\s+if=",                              # reformat, raw overwrite
    r"curl[^|]*\|\s*(sudo\s+)?(ba)?sh",                  # curl … | sh
    r"\bgit\s+push\b.*(--force|(\s|^)-f\b)",             # rewriting a remote
    r">\s*/dev/sd[a-z]",                                 # redirect onto a disk
]


def refuse(call, reason):
    """The default approver: say no. Nobody is attached, so nothing is approved."""
    return False


class Policy:
    """The permission gate; pass ``check`` to ``run_loop`` as ``before_tool``."""

    def __init__(self, mode="safe", approver=None):
        if mode not in MODES:
            raise ValueError("mode must be one of %s" % (MODES,))
        self.mode = mode
        self.approver = approver or refuse

    def check(self, call):
        """Return ``None`` to allow the call, or the reason it is blocked."""
        if call["name"] == "bash":
            pattern = denied(call.get("args", {}).get("command", ""))
            if pattern:  # first, and above every mode: yolo does not buy this
                return "the command matches the deny pattern %s" % pattern
        if call["name"] in READ_TOOLS or self.mode == "yolo":
            return None
        if self.mode == "read-only":
            return "%s can change things and this session is read-only" % call["name"]
        reason = "%s can change things outside this conversation" % call["name"]
        # `is True`, not truthiness: a half-written approver that falls off the
        # end returns None, and None must never read as a human saying yes.
        if self.approver(call, reason) is True:
            return None
        return "the human did not approve: %s" % reason


def denied(command):
    """Return the first deny pattern ``command`` matches, or ``None`` if it is clean."""
    for pattern in DENY_PATTERNS:
        if re.search(pattern, command):
            return pattern
    return None
