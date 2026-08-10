"""Day 3 -- context: fitting an unbounded task into a bounded window.

Concept this file teaches: the message list is the agent's mind, and it only
ever grows. Every reply and every tool result is re-sent on every later turn,
so a long task does not fail because the work was hard -- it fails because the
history got heavy, and the last turn it can afford is the one before the
finish. Compaction is the answer: when the transcript crosses a budget, the
model summarises its own past, and that summary stands in for it.

Design rules this file embodies:
  * The recent turns are never summarised. A summary is lossy by definition,
    and the next step depends on exact detail -- the path just written, the
    error just read. Old context can be a paragraph; recent context cannot.
  * Compaction is one model call with tools withheld. It is a reduction, not a
    turn: nothing said inside it should be able to reach the machine.
  * The slice that survives has to be a legal conversation by itself. A tool
    result whose call was just summarised away is an orphan, and a provider
    that pairs results with calls rejects the entire request -- so the harness
    would die of the very thing meant to save it.
  * Four characters to a token is a guess, and is meant to be. The only
    question here is "are we close?", which a guess answers for free where a
    real tokeniser costs a dependency, a download, and a per-turn delay.
  * It plugs into ``before_turn``, the socket the loop has held open since day
    1. The loop still knows nothing about budgets, and this file still knows
    nothing about tools.
"""

from . import provider

CHARS_PER_TOKEN = 4   # the standard rule of thumb for English and code
KEEP_RECENT = 6       # messages handed forward verbatim: roughly three exchanges
CLIP_CHARS = 500      # per message, when rendering the old half for the summariser

SUMMARY_SYSTEM = ("You compress agent transcripts. Preserve: the original task, "
                  "every file created or edited and its purpose, key decisions, "
                  "unresolved errors, and what remains to be done. Be dense and "
                  "factual.")


def estimate_tokens(messages):
    """Return a rough token count for ``messages``: total characters over four."""
    # str(message) counts the dict's own punctuation and keys as well as the
    # text. That overhead is not an error: the wire format adds its own, so the
    # guess lands closer than measuring the text alone would.
    return sum(len(str(message)) for message in messages) // CHARS_PER_TOKEN


def compact(model, messages, budget_tokens):
    """Return ``messages``, or a compacted list once it outgrows the budget.

    The head becomes one model-written summary; the last ``KEEP_RECENT``
    messages carry over untouched. The same list object comes back when
    nothing was done, so a caller can tell a no-op from a compaction.
    """
    if (estimate_tokens(messages) <= budget_tokens
            or len(messages) <= KEEP_RECENT + 1):
        return messages
    old, recent = messages[:-KEEP_RECENT], messages[-KEEP_RECENT:]
    # A tool result at the front of the kept slice answers a call that is about
    # to be summarised away. Push it back into the half being summarised -- so
    # what it said still reaches the model -- rather than shipping an orphan.
    while recent and recent[0]["role"] == "tool":
        old.append(recent.pop(0))
    summary = provider.complete(model, SUMMARY_SYSTEM,
                                [{"role": "user", "text": _transcript(old)}], None)
    return [{"role": "user",
             "text": "[Conversation so far, compacted]\n%s" % summary["text"]}] + recent


def _transcript(messages):
    """Render messages as a plain ``role: text`` transcript for the summariser."""
    # Plain text, not JSON: the summariser is reading this, not parsing it, and
    # every brace spent on structure is a brace not spent on content.
    lines = []
    for message in messages:
        who = message["role"]
        if message.get("name"):  # a tool result is only meaningful with its tool
            who = "%s(%s)" % (who, message["name"])
        text = (message.get("text") or "").strip()
        if len(text) > CLIP_CHARS:
            # One enormous read must not crowd out twenty small decisions.
            text = "%s… (+%d chars)" % (text[:CLIP_CHARS], len(text) - CLIP_CHARS)
        called = ", ".join(call["name"] for call in message.get("tool_calls") or [])
        if called:
            # Names only. Which tools ran is the shape of the work; the
            # arguments are already in the results below them.
            text = "%s [calls: %s]" % (text, called) if text else "[calls: %s]" % called
        lines.append("%s: %s" % (who, text))
    return "\n".join(lines)
