"""Day 3 -- skills: folders of instructions the agent loads only when it needs them.

Concept this file teaches: a skill is not code. It is a markdown file that
teaches the agent how this project wants a job done -- the review checklist, the
deploy steps, the brand voice -- and the whole mechanism is a directory listing
plus a read. What makes it worth building is *when* the reading happens. Every
skill costs one catalogue line in the system prompt, always; the body costs
nothing until the model asks for it. Ten skills you might need are cheaper than
one long prompt you mostly do not, and that trade is the entire idea.

Design rules this file embodies:
  * The catalogue advertises, the body instructs. A description has one job --
    to let the model decide whether this is the moment -- so a vague one is a
    skill that never loads, and the skill's author owns that outcome.
  * Skills are data, discovered from disk on every call. Adding one is making a
    directory, not editing this file, and never restarting anything. That is
    the whole reason the agent's behaviour can change with no code change.
  * A miss answers with the alternatives. "No skill named x" teaches a model to
    guess again; "no skill named x, here is what exists" ends the search in one
    turn, and matches how ``security.py`` refuses.
  * No cap on the body, unlike every tool in ``tools.py``. A skill is written by
    the human who owns the repository, not produced by the machine, so its
    length is an authoring decision rather than an untrusted input.
"""

import os

SKILLS_DIR = "skills"
SKILL_FILE = "SKILL.md"
FRONT_MATTER_LINES = 20        # how far into an unfenced file to look for a description
NO_DESCRIPTION = "(no description)"


def catalog(workdir):
    """Return ``{name: {"description", "path"}}`` for every skill under ``workdir``."""
    base = os.path.join(os.path.realpath(workdir), SKILLS_DIR)
    found = {}
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        path = os.path.join(base, name, SKILL_FILE)
        if os.path.isfile(path):  # a directory without one is not a skill, just a folder
            found[name] = {"description": _description(path), "path": path}
    return found


def catalog_prompt(workdir):
    """Return the catalogue as prompt text, or ``""`` when there are no skills."""
    found = catalog(workdir)
    if not found:
        return ""  # empty, not a header saying "none": absence should cost nothing
    lines = ["Skills available (load one with the use_skill tool when relevant):"]
    lines += ["- %s: %s" % (name, entry["description"])
              for name, entry in found.items()]
    return "\n".join(lines)


def read_skill(workdir, name):
    """Return the full text of a skill, or an error naming the ones that exist."""
    known = catalog(workdir)
    entry = known.get(name)
    if entry is None:
        return "ERROR: no skill named %s. Available: %s" % (
            name, ", ".join(known) or "none")
    return _read(entry["path"])


def _description(path):
    """Return the ``description:`` value from a skill's front matter, or a stand-in."""
    for line in _front_matter(_read(path)):
        if line.lower().startswith("description:"):
            # Split once: a description may well contain its own colon.
            return line.split(":", 1)[1].strip().strip("\"'") or NO_DESCRIPTION
    return NO_DESCRIPTION


def _front_matter(text):
    """Return the lines of a leading ``---`` block, else the head of the file."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for end, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                return lines[1:end]
    # No fence, or one nobody closed. Read the head anyway rather than refusing
    # on a formality: a description on line 2 of a plain file is still there.
    return lines[:FRONT_MATTER_LINES]


def _read(path):
    """Return the contents of ``path``, replacing anything that is not text."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()
