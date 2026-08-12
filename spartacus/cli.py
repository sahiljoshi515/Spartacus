"""Day 5 -- the command line: the first file a user meets, and the last one written.

Concept this file teaches: a harness with no front door is a library, and a
library is something only its author runs. Everything underneath is already
finished -- this file adds no capability at all. What it adds is a way in: two
of them, because the two ways people use an agent want opposite defaults. A
headless ``-p`` run has nobody sitting there to answer a permission prompt, so
asking would hang forever; an interactive session has a human watching, and
asking is the whole point of having them.

Design rules this file embodies:
  * The mode default is computed, not constant. ``safe`` when a human is
    present to approve, ``yolo`` when one is not -- and an explicit ``--mode``
    beats both, because a guess should never outrank an instruction.
  * Display belongs here and nowhere else. The loop emits events, the harness
    persists them, and this file is the only place that decides what a person
    should see: the reply in full, the call in one line, the result reduced to
    the line that tells you whether it worked.
  * Ctrl-C is a feature, not a crash. Day 4 made the transcript durable
    precisely so that abandoning a run costs nothing, so the interrupt handler
    says how to pick it back up rather than apologising.
  * Escape codes are conditional. Dimmed text through a pipe is not dim, it is
    ``\\033[2m`` in the middle of your grep output.
"""

import argparse
import os
import sys

from . import config, models, provider, security
from .harness import Harness

CLIP = 90  # characters of an argument line or result line worth showing

# Resolved once, at import: colour is for terminals, not for files and pipes.
_TTY = sys.stdout.isatty()
DIM = "\033[2m" if _TTY else ""
BOLD = "\033[1m" if _TTY else ""
RESET = "\033[0m" if _TTY else ""

BANNER = """%(bold)sspartacus%(reset)s  model %(model)s  mode %(mode)s
working in %(workdir)s -- the file tools cannot reach outside it
keys: %(providers)s  from %(config)s
/help for commands, /exit or Ctrl-D to leave, Ctrl-C to abandon a running task."""

HELP = """  /model            show the current model
  /model <name>     switch model; accepts an alias (%s)
  /models [vendor] [filter]   list what a vendor offers, live
  /mode <name>      switch permission mode (%s)
  /help             this list
  /exit             leave spartacus (so does Ctrl-D, or a bare "exit")
Anything else is a task for the agent.""" % (", ".join(sorted(models.ALIASES)),
                                             ", ".join(security.MODES))

# Typed at the prompt on their own, these mean goodbye rather than "do this".
FAREWELLS = ("exit", "quit", ":q")


def build_parser():
    """Return the argument parser, kept separate so it can be read on its own."""
    parser = argparse.ArgumentParser(
        prog="spartacus", description="A small, sharp coding agent.")
    parser.add_argument("-p", "--prompt",
                        help="run one task without a prompt loop, then exit")
    parser.add_argument("-d", "--workdir", default=".",
                        help="directory the agent is confined to (default: .)")
    parser.add_argument("-m", "--model",
                        help="model id (default: $SPARTACUS_MODEL, else built-in)")
    parser.add_argument("--mode", choices=security.MODES,
                        help="permission mode (default: safe, or yolo with -p)")
    parser.add_argument("--resume", action="store_true",
                        help="continue the newest session in the working directory")
    parser.add_argument("--max-turns", type=int, default=120,
                        help="model turns before the agent is told to wrap up")
    parser.add_argument("--list-models", action="store_true",
                        help="list the models each configured vendor offers, then exit")
    return parser


def main(argv=None):
    """Parse arguments, build the harness, and run headless or interactively."""
    args = build_parser().parse_args(argv)
    config.load()  # keys from ~/.config/spartacus/env, without beating real env vars
    if args.list_models:
        return list_models()
    # Nobody is watching a -p run, and security.refuse means an unattended
    # "safe" would block every write and call it a day.
    mode = args.mode or ("yolo" if args.prompt else "safe")
    # Resolve the alias here rather than deep in the provider, so the banner and
    # the session log both record the id that actually answered.
    try:
        model = models.resolve(args.model)[0] if args.model else None
    except ValueError as error:
        # Fail here, with the list, rather than as a puzzling 404 five turns in.
        print("spartacus: %s" % error, file=sys.stderr)
        return 2
    agent = Harness(args.workdir, model=model,
                    policy=security.Policy(mode, approver=ask),
                    on_event=show_event, max_turns=args.max_turns)
    if args.resume:
        if agent.resume():
            print("[resumed] %d messages from %s"
                  % (len(agent.messages), os.path.basename(agent.session_path)))
        else:
            print("[resume] nothing to continue in %s" % agent.workdir)
    if args.prompt:
        agent.run(args.prompt)
        return 0
    return interactive(agent)


def list_models():
    """Print what every configured vendor offers. Returns a shell exit code."""
    ready = models.configured()
    if not ready:
        print("No API keys found. Put them in %s, one KEY=value per line:"
              % config.CONFIG_PATH)
        for name, spec in sorted(models.PROVIDERS.items()):
            print("  %-10s %s" % (name, spec["keys"][0]))
        return 1
    for name in ready:
        try:
            found = provider.list_models(name)
        except Exception as error:  # one dead vendor must not hide the others
            print("\n%s: %s" % (name, error))
            continue
        print("\n%s (%d)" % (name, len(found)))
        for model in found:
            print("  %s" % model)
    return 0


def interactive(agent):
    """Run the prompt loop until Ctrl-D. Always returns 0: quitting is not failure."""
    print(BANNER % {"bold": BOLD, "reset": RESET, "model": agent.model,
                    "mode": agent.policy.mode, "workdir": agent.workdir,
                    "providers": ", ".join(models.configured()) or "none found",
                    "config": config.describe()})
    while True:
        try:
            task = input("\n%sspartacus>%s " % (BOLD, RESET)).strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()  # a stray Ctrl-C at the prompt clears the line and no more
            continue
        if not task:
            continue
        # A lone "exit" is a goodbye, not a task. Sending it to the model costs
        # an API call to be told it does not know what you meant.
        if task.lower() in FAREWELLS:
            return 0
        if task.startswith("/"):
            if command(agent, task):
                return 0
            continue
        try:
            agent.run(task)
        except KeyboardInterrupt:
            print("\n[interrupted] The session log is safe -- "
                  "spartacus --resume -d %s picks it up." % agent.workdir)
        except Exception as error:  # broad on purpose: see the note below
            # A REPL that dies of one HTTP 500 throws away the conversation it
            # was holding. Report and keep the prompt, exactly as the loop
            # turns a broken tool into text instead of a traceback.
            print("\n[error] %s: %s" % (type(error).__name__, error))


def show_models(vendor=None, match=None):
    """List models for one vendor, or a count per vendor when none is named.

    A bare ``/models`` used to print all 188 ids a three-vendor setup offers,
    comma-joined, which is not a list -- it is a wall. Naming a vendor is the
    common case, so unnamed prints the shape and tells you how to narrow it.
    """
    ready = models.configured()
    if not ready:
        print("  no API keys found -- see %s" % config.CONFIG_PATH)
        return
    if vendor and vendor not in models.PROVIDERS:
        print("  unknown vendor %r; try %s" % (vendor, ", ".join(ready)))
        return
    for name in [vendor] if vendor else ready:
        try:
            found = provider.list_models(name)
        except Exception as error:  # one dead vendor must not hide the others
            print("  %-10s %s" % (name, error))
            continue
        if match:
            found = [m for m in found if match.lower() in m.lower()]
        if not vendor:
            print("  %-10s %d models  (/models %s to list)" % (name, len(found), name))
            continue
        print("  %s (%d%s)" % (name, len(found), " matching %r" % match if match else ""))
        for model in found:
            print("    %s" % model)


def command(agent, line):
    """Handle a ``/`` command. Returns True when the loop should stop."""
    name, _, rest = line[1:].partition(" ")
    rest = rest.strip()
    if name in FAREWELLS:
        return True
    if name == "model" and not rest:
        print("  %s" % agent.model)
    elif name == "model":
        try:
            model, vendor = models.resolve(rest)
        except ValueError as error:
            print("  %s" % error)
            return
        # Swapping mid-session is safe because the transcript is neutral: the
        # translators rebuild each vendor's shape from it on every single call.
        agent.model = model
        print("  model is now %s (%s)" % (model, vendor))
    elif name == "models":
        show_models(*rest.split(None, 1) if rest else ())
    elif name == "mode" and rest in security.MODES:
        agent.policy = security.Policy(rest, approver=ask)
        print("  mode is now %s" % rest)
    elif name == "mode":
        print("  mode is %s (choose from %s)"
              % (agent.policy.mode, ", ".join(security.MODES)))
    else:
        print(HELP)


def show_event(kind, payload):
    """Print one loop event: replies plainly, calls on a line, results dimmed."""
    if kind == "assistant":
        if payload["text"]:
            print("\n%s" % payload["text"])
        for call in payload["tool_calls"]:
            print("  %s%s%s %s" % (BOLD, call["name"], RESET,
                                   _clip(_arguments(call["args"]))))
    elif kind == "tool_end":
        # One line, because the model already has the other four thousand; this
        # is here to tell a human "it worked" or "it did not".
        print("  %s%s%s" % (DIM, _clip(_first_line(payload["result"])), RESET))


def ask(call, reason):
    """Show the call and ask the human to approve it; anything but yes is no."""
    print("\n  %s%s%s wants to run" % (BOLD, call["name"], RESET))
    print("  %s" % _clip(_arguments(call.get("args") or {}), 400))
    print("  %s%s%s" % (DIM, reason, RESET))
    try:
        answer = input("  approve %s? [y/N] " % call["name"])
    except (EOFError, KeyboardInterrupt):
        print()  # a closed stdin is not consent
        return False
    return answer.strip().lower() in ("y", "yes")


def _arguments(args):
    """Render a call's arguments as one flat line."""
    return " ".join("%s=%s" % (name, str(value).replace("\n", "\\n"))
                    for name, value in args.items())


def _first_line(result):
    """Return the first non-empty line of a tool result, or a stand-in."""
    for line in str(result).splitlines():
        if line.strip():
            return line.strip()
    return "(no output)"


def _clip(text, limit=CLIP):
    """Shorten ``text`` to ``limit`` characters, marking what was cut."""
    return text if len(text) <= limit else "%s… (+%d)" % (text[:limit],
                                                          len(text) - limit)
