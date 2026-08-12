"""Day 1 -- the provider: the one place in Spartacus that knows the wire.

Concept: a harness needs exactly one translation boundary. Above it everything
speaks a neutral dialect of three message shapes; below it live Gemini's
``contents``, OpenAI's ``messages``, Anthropic's content blocks, three sets of
retry codes and three ways of spelling a tool call. A new vendor means editing
only this file -- which is the promise day 1 made, and this is it being kept.

The neutral format, in full:
    {"role": "user",      "text": str}
    {"role": "assistant", "text": str, "tool_calls": [{name, args, signature}]}
    {"role": "tool",      "name": str, "text": str}

Design rules: neutral in, neutral out, so no caller above ever sees a "part", a
"choice" or a "content block"; one network call inside one function, and
nothing else in the package opens a socket; transient failures retry with
backoff while everything else raises loudly, because a harness that swallows a
400 teaches the wrong lesson.

On tool-call identity: the neutral format pairs a result with its call by
*order*, which is all Gemini needs. OpenAI and Anthropic both want an explicit
id on each side. Rather than pollute the neutral format with ids that two
thirds of the code would ignore, the translators mint them deterministically
from the message index and match results to calls in the order they arrive --
the same invariant ``loop.py`` maintains and ``session.repair`` restores.
"""

import json
import os
import time
import urllib.error
import urllib.request

from . import config, models

# Kept for callers that predate multi-provider routing.
API_ROOT = models.PROVIDERS["gemini"]["base"] + "/models"
DEFAULT_MODEL = models.DEFAULT_MODEL
ANTHROPIC_VERSION = "2023-06-01"


def api_key(provider="gemini"):
    """Return the API key for ``provider``, loading the config file if needed."""
    config.load()  # lazy and idempotent: no file is touched until a key is wanted
    names = models.settings(provider)["keys"]
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError("No API key for %s: set %s (or put it in %s)."
                       % (provider, " or ".join(names), config.CONFIG_PATH))


def complete(model, system, messages, tools=None):
    """Call the model once and return ``{"text", "tool_calls", "usage"}``.

    ``tools``: a list of ``{"schema": ...}`` dicts, or None to forbid tool use.
    """
    model, provider = models.resolve(model)
    return _BACKENDS[provider](model, system, messages, tools)


def list_models(provider):
    """Return the model ids ``provider`` currently offers, newest listing first."""
    key = api_key(provider)
    base = models.settings(provider)["base"]
    if provider == "gemini":
        data = _get("%s/models?key=%s&pageSize=200" % (base, key), {})
        return [m["name"].split("/")[-1] for m in data.get("models") or []]
    if provider == "openai":
        data = _get("%s/models" % base, {"Authorization": "Bearer %s" % key})
        return sorted(m["id"] for m in data.get("data") or [])
    data = _get("%s/models" % base, {"x-api-key": key,
                                     "anthropic-version": ANTHROPIC_VERSION})
    return [m["id"] for m in data.get("data") or []]


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------

def _gemini(model, system, messages, tools):
    """Translate to Gemini's ``contents``, call it, and translate back."""
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": _to_wire(messages),
        "generationConfig": {"temperature": 0.4,
                             "maxOutputTokens": models.settings("gemini")["max_output"]},
    }
    if tools:
        body["tools"] = [{"functionDeclarations": [t["schema"] for t in tools]}]
    url = "%s/%s:generateContent?key=%s" % (API_ROOT, model, api_key("gemini"))
    data = _post(url, body, {})
    chunks, calls = [], []
    candidate = (data.get("candidates") or [{}])[0]
    for part in candidate.get("content", {}).get("parts") or []:
        if part.get("thought"):
            continue  # reasoning traces are not transcript text; never surface them
        if "text" in part:
            chunks.append(part["text"])
        if "functionCall" in part:
            # Gemini 3 hands back an opaque thought signature per call and wants
            # it verbatim next turn, so it rides along with the call itself.
            calls.append({"name": part["functionCall"].get("name", ""),
                          "args": part["functionCall"].get("args") or {},
                          "signature": part.get("thoughtSignature")})
    usage = data.get("usageMetadata") or {}
    return _reply(chunks, calls, usage.get("promptTokenCount", 0),
                  usage.get("candidatesTokenCount", 0))


def _to_wire(messages):
    """Translate neutral messages into Gemini ``contents`` entries."""
    wire = []
    for message in messages:
        role = message["role"]
        if role == "user":
            wire.append({"role": "user", "parts": [{"text": message["text"]}]})
        elif role == "assistant":
            parts = []
            if message.get("text"):
                parts.append({"text": message["text"]})  # omit empty text parts
            for call in message.get("tool_calls") or []:
                part = {"functionCall": {"name": call["name"], "args": call["args"]}}
                # Mandatory, not cosmetic: without the echoed signature Gemini 3
                # rejects the follow-up turn as a broken thought round-trip.
                if call.get("signature"):
                    part["thoughtSignature"] = call["signature"]
                parts.append(part)
            wire.append({"role": "model", "parts": parts})
        elif role == "tool":
            # Gemini has no tool role: output returns as a user turn, and the
            # functionResponse part is what marks it as output, not input.
            wire.append({"role": "user", "parts": [{"functionResponse": {
                "name": message["name"], "response": {"result": message["text"]}}}]})
    return wire


# --------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------

def _openai(model, system, messages, tools):
    """Translate to OpenAI chat completions, call it, and translate back."""
    body = {"model": model, "messages": _openai_wire(system, messages)}
    if tools:
        body["tools"] = [{"type": "function", "function": t["schema"]} for t in tools]
    data = _post("%s/chat/completions" % models.settings("openai")["base"], body,
                 {"Authorization": "Bearer %s" % api_key("openai")})
    reply = (data.get("choices") or [{}])[0].get("message") or {}
    calls = []
    for call in reply.get("tool_calls") or []:
        function = call.get("function") or {}
        calls.append({"name": function.get("name", ""),
                      "args": _loads(function.get("arguments")),
                      "signature": None})
    usage = data.get("usage") or {}
    return _reply([reply.get("content") or ""], calls,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def _openai_wire(system, messages):
    """Translate neutral messages into OpenAI ``messages`` entries."""
    wire = [{"role": "system", "content": system}] if system else []
    pending = []
    for index, message in enumerate(messages):
        role = message["role"]
        if role == "user":
            wire.append({"role": "user", "content": message["text"]})
        elif role == "assistant":
            calls = message.get("tool_calls") or []
            pending = _ids(index, len(calls))
            # content must be a string when there are no tool calls: OpenAI
            # rejects an assistant turn that is empty in both fields at once.
            entry = {"role": "assistant", "content": message.get("text") or ""}
            if calls:
                entry["tool_calls"] = [
                    {"id": pending[n], "type": "function",
                     "function": {"name": call["name"],
                                  "arguments": json.dumps(call["args"])}}
                    for n, call in enumerate(calls)]
            wire.append(entry)
        elif role == "tool":
            wire.append({"role": "tool", "content": message["text"],
                         "tool_call_id": pending.pop(0) if pending else "call_orphan"})
    return wire


# --------------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------------

def _anthropic(model, system, messages, tools):
    """Translate to Anthropic content blocks, call it, and translate back."""
    body = {"model": model, "messages": _anthropic_wire(messages),
            "max_tokens": models.settings("anthropic")["max_output"]}
    if system:
        body["system"] = system  # a parameter here, not a message
    if tools:
        body["tools"] = [{"name": t["schema"]["name"],
                          "description": t["schema"].get("description", ""),
                          "input_schema": t["schema"]["parameters"]} for t in tools]
    data = _post("%s/messages" % models.settings("anthropic")["base"], body,
                 {"x-api-key": api_key("anthropic"),
                  "anthropic-version": ANTHROPIC_VERSION})
    chunks, calls = [], []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            chunks.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append({"name": block.get("name", ""),
                          "args": block.get("input") or {}, "signature": None})
    usage = data.get("usage") or {}
    return _reply(chunks, calls, usage.get("input_tokens", 0),
                  usage.get("output_tokens", 0))


def _anthropic_wire(messages):
    """Translate neutral messages into Anthropic turns of content blocks."""
    wire = []
    pending = []
    for index, message in enumerate(messages):
        role = message["role"]
        if role == "user":
            wire.append({"role": "user",
                         "content": [{"type": "text", "text": message["text"]}]})
        elif role == "assistant":
            calls = message.get("tool_calls") or []
            pending = _ids(index, len(calls))
            blocks = []
            if message.get("text"):
                blocks.append({"type": "text", "text": message["text"]})
            for n, call in enumerate(calls):
                blocks.append({"type": "tool_use", "id": pending[n],
                               "name": call["name"], "input": call["args"]})
            # An assistant turn may not be empty, and a compacted transcript can
            # hand us one that is.
            wire.append({"role": "assistant",
                         "content": blocks or [{"type": "text", "text": "(no content)"}]})
        elif role == "tool":
            block = {"type": "tool_result", "content": message["text"],
                     "tool_use_id": pending.pop(0) if pending else "call_orphan"}
            # Anthropic strictly alternates user and assistant, so several
            # results for one turn have to arrive as blocks of a single message.
            if _is_results_turn(wire):
                wire[-1]["content"].append(block)
            else:
                wire.append({"role": "user", "content": [block]})
    return wire


def _is_results_turn(wire):
    """True when the last wire entry is a user turn already holding tool results."""
    return (wire and wire[-1]["role"] == "user" and wire[-1]["content"]
            and wire[-1]["content"][0].get("type") == "tool_result")


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------

_BACKENDS = {"gemini": _gemini, "openai": _openai, "anthropic": _anthropic}


def _ids(index, count):
    """Mint deterministic tool-call ids for one assistant turn."""
    return ["call_%d_%d" % (index, n) for n in range(count)]


def _loads(raw):
    """Parse a JSON argument blob, tolerating a model that sent nothing useful."""
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}  # a malformed argument is the tool's problem to report, not a crash


def _reply(chunks, calls, prompt_tokens, output_tokens):
    """Assemble the neutral reply every backend returns."""
    return {"text": "".join(c for c in chunks if c).strip(), "tool_calls": calls,
            "usage": {"input": prompt_tokens, "output": output_tokens}}


def _post(url, body, headers, retries=5):
    """POST JSON, retrying transient failures; raise ``RuntimeError`` otherwise."""
    return _request(url, headers, json.dumps(body).encode(), retries)


def _get(url, headers, retries=3):
    """GET JSON, with the same retry policy as a POST."""
    return _request(url, headers, None, retries)


def _request(url, headers, payload, retries):
    """Perform one HTTP call with backoff on the codes worth retrying."""
    sending = {"Content-Type": "application/json"}
    sending.update(headers)
    for attempt in range(retries):
        req = urllib.request.Request(url, payload, sending)
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:  # subclass of URLError: catch first
            if error.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            detail = error.read()[:400].decode("utf-8", "replace")
            raise RuntimeError("HTTP %s from %s: %s"
                               % (error.code, _host(url), detail)) from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError("%s unreachable: %s" % (_host(url), error)) from error


def _host(url):
    """Return the hostname of ``url``, for error messages that name the vendor."""
    return url.split("//", 1)[-1].split("/", 1)[0]
