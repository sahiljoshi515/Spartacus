"""Day 1 -- the loop: think, act, observe, repeat.

Concept this file teaches: an agent is a while-loop around a stateless model.
The model remembers nothing between calls, so the message list *is* the agent's
mind. Every reply and every tool result must be appended, in order, or the next
turn reasons about a history that never happened.

Design rules this file embodies:
  * The loop owns control flow and nothing else. Permission lives in
    ``before_tool``, display lives in ``on_event``, history management lives in
    ``before_turn`` -- the loop only calls them at the right moment.
  * A tool fault is data, not a crash. The error text becomes the tool result so
    the model can read it and choose differently. The loop never dies because a
    tool did.
  * Messages are mutated in place, so a caller holding the list (a session, a
    logger, a UI) always sees the live transcript.
"""

from . import provider


def run_loop(model, system, messages, tools, on_event, before_tool,
             max_turns=80, before_turn=None):
    """Drive the agent until the model replies without calling a tool.

    ``tools`` maps name -> Tool, where a Tool exposes ``.spec`` (a
    ``{"schema": ...}`` dict) and ``.run`` (a callable taking keyword
    arguments). ``on_event(kind, payload)`` fires with "assistant" after each
    model reply and "tool_start"/"tool_end" around each execution.
    ``before_tool(call)`` returns None to allow or a reason string to block.
    ``before_turn(messages)``, when given, returns the list to send instead;
    it is unused on day 1 and is where day 3 plugs in compaction.

    Returns the model's final text.
    """
    for _ in range(max_turns):
        if before_turn:
            messages[:] = before_turn(messages)  # in place: the caller must see it
        reply = provider.complete(model, system, messages,
                                  [tool.spec for tool in tools.values()])
        messages.append({"role": "assistant", "text": reply["text"],
                         "tool_calls": reply["tool_calls"]})
        on_event("assistant", reply)
        if not reply["tool_calls"]:
            return reply["text"]
        for call in reply["tool_calls"]:
            on_event("tool_start", call)
            result = _execute(call, tools, before_tool)
            messages.append({"role": "tool", "name": call["name"],
                             "text": str(result)})
            on_event("tool_end", {"call": call, "result": result})

    # Out of turns. Ask for a summary with tools withheld, so the model cannot
    # start another round of work it will not be allowed to finish.
    messages.append({"role": "user", "text": "Turn limit reached; wrap up now."})
    final = provider.complete(model, system, messages, None)
    messages.append({"role": "assistant", "text": final["text"], "tool_calls": []})
    on_event("assistant", final)
    return final["text"]


def _execute(call, tools, before_tool):
    """Run one tool call behind the permission gate, turning faults into text."""
    reason = before_tool(call)
    if reason:
        return "BLOCKED: %s" % reason
    tool = tools.get(call["name"])
    if tool is None:
        return "ERROR: unknown tool %s" % call["name"]
    try:
        return tool.run(**call["args"])
    except Exception as error:  # deliberately broad: the model handles the report
        return "ERROR: %s: %s" % (type(error).__name__, error)
