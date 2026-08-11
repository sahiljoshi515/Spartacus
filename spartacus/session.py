"""Day 4 -- sessions: the transcript on disk, and what to do when it is torn.

Concept this file teaches: an agent that cannot survive its own process is a
demo. The message list is the agent's mind, and until now it lived only in RAM,
so a closed laptop threw away an hour of work halfway through. Writing each
message as it lands turns a killed run into a resumable one -- but only if the
format survives being killed mid-write, which is the part people skip.

Design rules this file embodies:
  * Append-only, one JSON object per line. A file rewritten in place can be
    corrupted anywhere; a file only ever appended to can be corrupted in exactly
    one place, the end, and that is a place you can reason about. The single
    exception proves the rule: a write discards a torn final line first, which
    is the only way the guarantee survives contact with a second crash.
  * A torn tail is expected, not exceptional. ``kill -9`` lands mid-``write``
    eventually, and the honest answer is to keep every line that parsed and
    stop at the one that did not -- not to raise, and never to guess at what
    the half-written line meant.
  * Repair on load, because a resumed transcript must be *legal* before it is
    useful. A provider rejects an assistant turn whose tool calls have no
    matching results, so a crash between "the model asked" and "the tool
    answered" comes back as an HTTP 400 rather than as lost work. Restarting
    must not resurrect the crash in a new shape.
  * The invented results say plainly that they were invented. The model reads
    "interrupted before this ran" and retries the call; a fabricated success
    would have it build on something that never happened.
"""

import json
import os
import re
import time

SESSION_DIR = ".spartacus/sessions"
SLUG_MAX = 40  # characters of the label kept in the filename
INTERRUPTED = "Interrupted before this ran (process restarted)."


def new_session(workdir, label="session"):
    """Create the session directory, keep it out of git, and return a log path."""
    base = os.path.join(os.path.realpath(workdir), SESSION_DIR)
    os.makedirs(base, exist_ok=True)
    _self_ignore(os.path.dirname(base))
    # The timestamp leads so the directory sorts chronologically in any listing;
    # the slug follows so a human can tell the runs apart without opening them.
    name = "%d-%s.jsonl" % (int(time.time()), _slugify(label))
    return os.path.join(base, name)


def append(path, message):
    """Append one message to the log as a single JSON line."""
    _drop_torn_line(path)
    with open(path, "a", encoding="utf-8") as handle:
        # ensure_ascii=False keeps the log readable: a transcript full of
        # — escapes is a transcript nobody debugs by eye.
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def read(path):
    """Return the messages already written to ``path``, stopping at a torn line."""
    messages = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                messages.append(json.loads(line))
            except ValueError:
                break  # a half-written final line: everything before it is good
    return messages


def load(path):
    """Return the messages in ``path``, stopping at a torn line and repaired."""
    return repair(read(path))


def latest(workdir):
    """Return the most recently written session log, or ``None`` if there is none."""
    base = os.path.join(os.path.realpath(workdir), SESSION_DIR)
    logs = [os.path.join(base, name) for name in os.listdir(base)
            if name.endswith(".jsonl")] if os.path.isdir(base) else []
    # By modification time, not by name: the newest log is the one last written
    # to, which is what "resume where I left off" actually means.
    return max(logs, key=os.path.getmtime) if logs else None


def repair(messages):
    """Answer every tool call the crash left hanging, so the transcript is legal."""
    last = _last_assistant(messages)
    if last is None:
        return messages
    calls = messages[last].get("tool_calls") or []
    # Results always follow their call immediately, so counting the tool
    # messages after the last assistant turn says how far execution got.
    answered = sum(1 for message in messages[last + 1:] if message["role"] == "tool")
    for call in calls[answered:]:
        messages.append({"role": "tool", "name": call["name"], "text": INTERRUPTED})
    return messages


def _self_ignore(directory):
    """Write a ``.gitignore`` covering ``directory`` whole, unless one is there.

    The session log lives inside the working directory, and the working
    directory is very often a repository the agent was pointed at. Without
    this, the human's next ``git add -A`` stages their own transcripts -- and a
    transcript quotes every file the agent read, which is a far wider blast
    radius than "some logs". The self-ignoring ``*`` is the ordinary idiom for
    a tool-owned directory, and it is the half of this problem this file can
    solve on its own: keeping the logs out of the agent's own ``grep`` needs
    ``IGNORED_DIRS`` in ``tools.py``.
    """
    path = os.path.join(directory, ".gitignore")
    if os.path.exists(path):
        return  # never clobber: past this point the file belongs to the human
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Written by spartacus. Session logs are not source.\n*\n")


def _drop_torn_line(path):
    """Remove a half-written final line, so the next append is not welded to it.

    ``kill -9`` mid-``write`` leaves a line with no newline. Appending straight
    onto it fuses the new message to the fragment, and because ``read`` keeps
    only what precedes the first unparseable line, everything written from then
    on is silently unreachable -- the log grows and the transcript does not.
    Cutting the fragment loses nothing, since it was already past the point
    where reading stops, and it restores the property the rest of this file
    relies on: corruption lives at the end, and only until the next write.
    """
    if not os.path.exists(path):
        return
    with open(path, "rb+") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            return
        handle.seek(size - 1)
        if handle.read(1) == b"\n":
            return  # the common path, and O(1): the log ends on a line boundary
        handle.seek(0)
        # At most once per file: after this, every line ends in a newline again.
        handle.truncate(handle.read().rfind(b"\n") + 1)


def _last_assistant(messages):
    """Return the index of the final assistant message, or ``None`` if there is none."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "assistant":
            return index
    return None


def _slugify(label):
    """Reduce ``label`` to lowercase alphanumerics and dashes, fit for a filename."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    # Clip first, then strip again: cutting at 40 can leave a trailing dash.
    return slug[:SLUG_MAX].strip("-") or "session"
