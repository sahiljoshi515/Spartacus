"""Day 2 -- tools: the schema the model reads and the code it fires, from one function.

Concept this file teaches: a tool is a contract in two halves, and the model
only ever sees one of them. Day 1 typed both halves out by hand, where they were
free to drift apart -- a renamed argument in ``run`` and the model keeps calling
the old name forever. Here the decorator derives the schema from the function's
own signature, so the only way to change what the model is told is to change the
code it triggers.

Design rules this file embodies:
  * Every parameter is declared as a string. The model emits whatever JSON
    scalar it pleases, so coercion happens once, at the tool boundary, inside
    the tool -- and a bad argument is allowed to raise, because the loop turns
    the raise into a sentence the model can read.
  * Every model-supplied path goes through one ``resolve``. A containment check
    written twice is a containment check with a hole in it.
  * Every tool returns text a model can act on: success says what changed, a
    fault says what to do instead. Nothing here prints, and nothing here
    decides whether it was allowed to run -- that is ``security.py``.
  * Output is capped everywhere: lines, characters, matches. An uncapped result
    does not merely flood the terminal; it is re-sent as input on every later
    turn, so one unbounded read is billed again for the rest of the run.
"""

import fnmatch
import inspect
import os
import re
import subprocess
import typing
from dataclasses import dataclass

READ_MAX_LINES = 4000     # read_file: numbered lines kept before truncating
BASH_MAX_CHARS = 12000    # bash: combined output kept before the middle is cut
LIST_MAX_FILES = 500      # list_files: paths per call
GREP_MAX_HITS = 200       # grep: matching lines per call
GREP_MAX_WIDTH = 200      # grep: characters kept per matching line
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


@dataclass
class Tool:
    """A capability in two halves: the ``spec`` a model reads, the ``run`` it fires."""

    name: str
    spec: dict
    run: typing.Callable


def tool(description, **params):
    """Return a decorator turning a function into a ``Tool`` with a derived schema.

    Each keyword names one of the function's parameters and supplies the
    description the model reads; parameters with defaults become optional.
    """
    def decorate(fn):
        args = inspect.signature(fn).parameters
        undocumented = [name for name in args if name not in params]
        if undocumented:  # import-time, because a schema typo is unfixable later
            raise TypeError("%s: no description for %s" % (fn.__name__, undocumented))
        return Tool(fn.__name__, {"schema": {
            "name": fn.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                # Strings throughout, deliberately: see the design rules above.
                "properties": {name: {"type": "string", "description": params[name]}
                               for name in args},
                "required": [name for name, arg in args.items()
                             if arg.default is inspect.Parameter.empty],
            },
        }}, fn)
    return decorate


def core_tools(workdir):
    """Return the six file-and-shell tools, each confined to ``workdir``."""
    root = os.path.realpath(workdir)

    def resolve(path):
        """Return the absolute path inside ``root``, or raise ``PermissionError``."""
        # realpath first, so "a/../../etc/passwd" and a symlink out are the same
        # question. Comparing the resolved strings is what makes ".." harmless.
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            raise PermissionError("%r escapes the working directory" % path)
        return full

    def walk():
        """Yield ``(full, relative)`` for each file under ``root``, pruning noise."""
        for base, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)  # prunes
            for name in sorted(names):
                rel = os.path.relpath(os.path.join(base, name), root)
                try:
                    full = resolve(rel)
                except PermissionError:
                    continue  # a symlink inside the tree can still point outside
                yield full, rel

    @tool("Read a file, with line numbers",
          path="File to read, relative to the working directory")
    def read_file(path):
        """Return the file numbered ``N<TAB>line``, truncated past the line cap."""
        with open(resolve(path), encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        numbered = ["%d\t%s" % (n, line)
                    for n, line in enumerate(lines[:READ_MAX_LINES], 1)]
        if len(lines) > READ_MAX_LINES:
            numbered.append("... truncated at %d lines; the file has %d"
                            % (READ_MAX_LINES, len(lines)))
        return "\n".join(numbered)

    @tool("Create or overwrite a file",
          path="File to write, relative to the working directory",
          content="Complete new contents of the file")
    def write_file(path, content):
        """Write ``content`` to ``path``, creating any missing parent directories."""
        full = resolve(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(content)
        return "Wrote %d chars to %s" % (len(content), path)

    @tool("Replace an exact snippet in a file, which must appear exactly once",
          path="File to edit, relative to the working directory",
          old="Snippet to replace, copied exactly, including indentation",
          new="Text to put in its place")
    def edit_file(path, old, new):
        """Replace ``old`` with ``new``, refusing zero or several matches."""
        full = resolve(path)
        with open(full, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        # Uniqueness is the whole safety property: an ambiguous snippet edited
        # at its first match is a silent, wrong edit, so it is a fault instead.
        found = text.count(old)
        if found == 0:
            return "ERROR: snippet not found — read the file and copy it exactly"
        if found > 1:
            return ("ERROR: snippet appears %d times — include more context to "
                    "make it unique" % found)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new, 1))
        return "Edited %s" % path

    @tool("Run a shell command in the working directory",
          command="Command line, run through the shell",
          timeout="Seconds to wait before killing it")
    def bash(command, timeout="120"):
        """Run ``command`` and return its combined output, capped and never raising."""
        try:
            done = subprocess.run(command, shell=True, cwd=root, timeout=float(timeout),
                                  capture_output=True, text=True, errors="replace")
        except subprocess.TimeoutExpired:
            # A kill loses the output, so the timeout itself is the report.
            return "ERROR: timed out after %ss" % timeout
        # stdout and stderr interleave in one stream because the model wants the
        # traceback next to the output that preceded it, not in a second field.
        output = (done.stdout + done.stderr).strip()
        if len(output) > BASH_MAX_CHARS:
            keep = BASH_MAX_CHARS // 2
            output = "%s\n... %d characters cut ...\n%s" % (
                output[:keep], len(output) - BASH_MAX_CHARS, output[-keep:])
        # An empty string reads as failure to a model; an exit code does not.
        return output or "(exit %d, no output)" % done.returncode

    @tool("List files in the working directory matching a glob",
          pattern="Glob such as '**/*.py'; matched against path and filename")
    def list_files(pattern="**/*"):
        """Return matching paths, sorted, capped, one per line."""
        found = [rel for _, rel in walk() if _matches(rel, pattern)]
        shown = found[:LIST_MAX_FILES]
        if len(found) > LIST_MAX_FILES:
            shown.append("... and %d more" % (len(found) - LIST_MAX_FILES))
        return "\n".join(shown) or "(no files match %s)" % pattern

    @tool("Search file contents for a regular expression",
          regex="Python regular expression to search for",
          pattern="Glob limiting which files are searched")
    def grep(regex, pattern="*"):
        """Return ``path:lineno: text`` for each matching line, clipped and capped."""
        matcher = re.compile(regex)
        hits = []
        for full, rel in walk():
            if len(hits) >= GREP_MAX_HITS or not _matches(rel, pattern):
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as handle:
                    for lineno, line in enumerate(handle, 1):
                        if matcher.search(line):
                            hits.append("%s:%d: %s"
                                        % (rel, lineno, line.strip()[:GREP_MAX_WIDTH]))
                            if len(hits) >= GREP_MAX_HITS:
                                break
            except OSError:
                continue  # unreadable file: a hole in the results, not a failure
        return "\n".join(hits) or "(no matches for %s)" % regex

    return [read_file, write_file, edit_file, bash, list_files, grep]


def _matches(rel, pattern):
    """Match a relative path against ``pattern``, treating ``**/`` as "any depth"."""
    # fnmatch has no ** concept, so it reads "**/*" as needing a literal "/" and
    # would hide every top-level file. Strip that prefix and try the basename
    # too, which is what a shell glob means by it.
    stem = pattern[3:] if pattern.startswith("**/") else pattern
    return (fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, stem)
            or fnmatch.fnmatch(os.path.basename(rel), stem))
