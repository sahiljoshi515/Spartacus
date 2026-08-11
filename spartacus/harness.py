"""Day 4 -- the harness: one object that holds the whole week together.

Concept this file teaches: every day so far built a part that knows nothing
about the others. The loop does not know what a budget is; ``context`` does not
know what a tool is; ``security`` does not know what a session is. That
independence is why each file fits on a screen -- and it means somebody has to
do the wiring. This is that somebody, and it is the only file in the package
that imports nearly all the rest.

Design rules this file embodies:
  * Composition, not logic. Almost nothing here is an algorithm; it is
    arguments being handed to the file that owns each decision. When this class
    starts making choices of its own, the week's structure has begun to rot.
  * Every socket the loop opened gets filled here, and nowhere else:
    ``before_tool`` is the policy, ``before_turn`` is compaction, ``on_event``
    is the caller's display with persistence spliced in front of it.
  * A child harness never persists. A sub-agent that wrote its own session log
    would leave *its* log as the newest in the directory, and the next
    ``resume`` would silently continue the child's task instead of yours. The
    parent owns the record; the children are weather.
  * The session is written as the run happens, not at the end. A log flushed on
    exit is a log you do not have precisely when you need it -- after a crash.
"""

import os

from . import context, loop, memory, provider, security, session, skills, tools
from .subagent import subagent_tool

# The contract names the lowercase form; the shell convention is the uppercase
# one, and provider.py already reads two names for one key, so do the same here.
MODEL_ENV = ("spartacus_MODEL", "SPARTACUS_MODEL")
LABEL_CHARS = 32  # characters of the opening task kept in the session filename


class Harness:
    """A configured agent: tools, prompt, policy, budget, and a session on disk."""

    def __init__(self, workdir=".", model=None, policy=None, extra_tools=None,
                 system_extra="", on_event=None, budget_tokens=600_000,
                 max_turns=120, session_path=None, enable_subagents=True,
                 persist=True, _depth=0):
        # expanduser before realpath: realpath does not expand "~", and the
        # makedirs below is unconditional, so "~/code" would otherwise create a
        # directory literally named "~" and work in it. A typo'd workdir must
        # not silently become a real, empty, wrong one.
        self.workdir = os.path.realpath(os.path.expanduser(workdir))
        os.makedirs(self.workdir, exist_ok=True)
        self.model = model or _env_model() or provider.DEFAULT_MODEL
        # Deliberately "yolo", inverting security.py's own "safe" default, and
        # worth saying out loud: an unattended Harness has unrestricted
        # write_file, edit_file and bash in this directory, behind nothing but
        # six deny regexes that security.py itself calls a speed bump. The
        # default suits a harness driven by a script with nobody to ask; pass
        # security.Policy() to get the asking kind back.
        self.policy = policy or security.Policy("yolo")
        self.on_event = on_event or _silent
        self.budget_tokens = budget_tokens
        self.max_turns = max_turns
        self.session_path = session_path
        self.persist = persist
        self.depth = _depth
        self.messages = []
        self._recorded = 0  # messages already written to the session log
        self.tools = self._build_tools(extra_tools, enable_subagents)
        self.system = memory.build_system_prompt(self.workdir,
                                                 self._prompt_extra(system_extra))

    def resume(self, path=None):
        """Load a session log into this harness; True when it held any messages."""
        path = path or session.latest(self.workdir)
        if path is None:
            return False
        # Read and repair in two steps, rather than calling session.load, so the
        # count of what is already on disk is exact. What ``repair`` invents has
        # to be written too, or the hole it patches reopens on the next load --
        # and by then it is buried mid-transcript, where the tail-only repair
        # will never reach it again. Guessing which messages were invented (by
        # matching their text) instead re-writes them on every resume, which
        # answers two tool calls four times and earns the 400 this prevents.
        self.messages = session.read(path)
        # Adopt the path only once it has actually been read, so a failed read
        # leaves the harness where it was instead of aimed at a file it cannot
        # open -- where the next run() would quietly append to it.
        self.session_path = path
        self._recorded = len(self.messages)
        self.messages = session.repair(self.messages)
        self._record()
        return bool(self.messages)

    def run(self, task):
        """Run one task to completion and return the agent's final text."""
        if self.persist and self.session_path is None:
            self.session_path = session.new_session(self.workdir, task[:LABEL_CHARS])
        self.messages.append({"role": "user", "text": task})
        self._record()
        answer = loop.run_loop(self.model, self.system, self.messages, self.tools,
                               self._event, self.policy.check,
                               max_turns=self.max_turns,
                               before_turn=self._before_turn)
        self._record()  # a belt-and-braces flush: every append is already evented
        return answer

    def _build_tools(self, extra_tools, enable_subagents):
        """Assemble the toolset: the six core tools, plus what this week added."""
        built = tools.core_tools(self.workdir)

        @tools.tool("Save a durable fact about this project for every future session",
                    note="One short sentence worth remembering")
        def remember(note):
            return memory.remember(self.workdir, note)

        built.append(remember)

        if skills.catalog(self.workdir):  # no skills, no tool to load them with
            @tools.tool("Load a skill's full instructions, then follow them",
                        name="Skill name, exactly as listed in your system prompt")
            def use_skill(name):
                return skills.read_skill(self.workdir, name)

            built.append(use_skill)

        if enable_subagents:
            built.append(subagent_tool(self._child, self.depth))

        built.extend(extra_tools or [])  # the caller's tools win on a name clash
        return {item.name: item for item in built}

    def _child(self, depth):
        """Build the ephemeral sub-agent that ``spawn_agent`` delegates to."""
        return Harness(self.workdir, model=self.model, policy=self.policy,
                       on_event=self.on_event, budget_tokens=self.budget_tokens,
                       max_turns=self.max_turns, persist=False, _depth=depth)

    def _prompt_extra(self, system_extra):
        """Join the skills catalogue and the caller's section, skipping blanks."""
        return "\n\n".join(part for part in
                           (skills.catalog_prompt(self.workdir), system_extra) if part)

    def _before_turn(self, messages):
        """Hold the history inside the budget; the loop uses what comes back."""
        compacted = context.compact(self.model, messages, self.budget_tokens)
        # Rewind the write cursor here, and only here, because this is the one
        # instant when the live list is exactly what has been written: the loop
        # has not appended this turn's reply yet. Clamping later -- inside
        # _record, once the reply has landed -- would clamp to a length that
        # already counts it, and that message would never be written at all.
        self._recorded = min(self._recorded, len(compacted))
        return compacted

    def _event(self, kind, payload):
        """Persist whatever the loop just appended, then tell the caller."""
        self._record()
        self.on_event(kind, payload)

    def _record(self):
        """Append every message added since the last call to the session log."""
        if not self.persist or self.session_path is None:
            return
        # No clamping here: _before_turn owns the cursor whenever the list
        # shrinks. The log keeps everything that ever happened, including the
        # history compaction folded into a summary -- it is the record, not the
        # window the model sees, and those are allowed to disagree.
        for message in self.messages[self._recorded:]:
            session.append(self.session_path, message)
        self._recorded = len(self.messages)


def _env_model():
    """Return the model named in the environment, or ``None`` if none is set."""
    for name in MODEL_ENV:
        if os.environ.get(name):
            return os.environ[name]
    return None


def _silent(kind, payload):
    """The default ``on_event``: a harness with nobody watching says nothing."""
