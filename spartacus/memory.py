"""Day 3 -- memory: the part of the agent that outlives the conversation.

Concept this file teaches: there are two kinds of memory and they are not the
same file. The message list is working memory -- vivid, expensive, and gone the
moment the process exits. This is the other kind: a markdown file in the
working directory, read back into the system prompt at the start of every run.
Nothing here is clever. That is the lesson. Durable memory is a text file the
human can open, edit, and delete, and the reason it works is that the system
prompt is rebuilt from disk every single time.

Design rules this file embodies:
  * The prompt is assembled, not stored. Base instructions, then the machine
    the agent is standing on, then whatever the project has learned, then
    whatever the caller adds -- so a fact written in one run is simply present
    in the next, with no retrieval step to get wrong.
  * The memory file is the human's, not the agent's. Markdown, one dash per
    fact, in the working directory where it can be read and pruned. A memory
    the human cannot audit is a memory the agent can quietly poison.
  * Say the platform and the real, resolved working directory out loud. A model
    guessing between ``ls`` and ``dir``, or writing to a path one symlink away
    from where it thinks it is, wastes turns on a question one line answers.
  * The base prompt is behaviour, not personality. Every line in it exists to
    stop a specific failure this harness has actually seen: narrating instead
    of acting, assuming instead of reading, and retrying a broken call forever.
"""

import os
import sys

MEMORY_FILE = "Spartacus.md"

BASE_PROMPT = """You are spartacus, a small, sharp coding agent. You work inside \
one directory, using the tools you have been given and nothing else.

Act, do not narrate. Run the tool instead of describing the tool you would run.
Inspect before you assume: read the file, list the directory, check what is \
actually there rather than what you expect.
Prefer edit_file for a small change; rewrite a whole file only when you mean to \
replace it.
Verify after you build. Run it, or read it back, and report only what you have \
actually seen.
Never repeat a failing call unchanged. Read the error, then change the call or \
change the approach.
When the task is complete, reply with a short summary and stop calling tools."""


def build_system_prompt(workdir, extra=""):
    """Return the base prompt, the environment, project memory, and ``extra``."""
    root = os.path.realpath(workdir)
    sections = [BASE_PROMPT,
                "Platform: %s. Working directory: %s" % (sys.platform, root)]
    remembered = _read(os.path.join(root, MEMORY_FILE))
    if remembered:
        sections.append("Project memory (%s):\n%s" % (MEMORY_FILE, remembered))
    if extra:  # the caller's own section: day 3 passes the skills catalogue here
        sections.append(extra)
    return "\n\n".join(sections)


def remember(workdir, note):
    """Append ``note`` to the project memory file as one dashed line."""
    path = os.path.join(os.path.realpath(workdir), MEMORY_FILE)
    with open(path, "a", encoding="utf-8") as handle:
        # Stripped, because one fact per line is the whole format: a note that
        # arrives with its own newline would silently start a second bullet.
        handle.write("- %s\n" % note.strip())
    return "Remembered in %s" % MEMORY_FILE


def _read(path):
    """Return the contents of ``path`` stripped, or ``""`` if it is not there."""
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read().strip()
