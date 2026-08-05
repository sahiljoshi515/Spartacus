"""Day 1 -- the provider: the one place in Spartacus that knows the wire.

Concept: a harness needs exactly one translation boundary. Above it everything
speaks a neutral dialect of three message shapes; below it lives Gemini's JSON,
its retry codes, and its quirks. A new vendor means editing only this file.

The neutral format, in full:
    {"role": "user",      "text": str}
    {"role": "assistant", "text": str, "tool_calls": [{name, args, signature}]}
    {"role": "tool",      "name": str, "text": str}

Design rules: neutral in, neutral out, so no caller above ever sees a "part" or
a "candidate"; one network call inside one function, and nothing else in the
package opens a socket; transient failures retry with backoff while everything
else raises loudly, because a harness that swallows a 400 teaches the wrong
lesson.
"""

import json
import os
import time
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-pro-preview"


def api_key():
    """Return the Gemini API key: ``SPARTACUS_API_KEY``, else ``GEMINI_API_KEY``."""
    # The harness-specific name wins, so Spartacus can hold its own key on a
    # machine where other Gemini tools already set GEMINI_API_KEY.
    key = os.environ.get("SPARTACUS_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("No API key: set SPARTACUS_API_KEY or GEMINI_API_KEY.")
    return key


def complete(model, system, messages, tools=None):
    """Call the model once and return ``{"text", "tool_calls", "usage"}``.

    ``tools``: a list of ``{"schema": ...}`` dicts, or None to forbid tool use.
    """
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": _to_wire(messages),
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 65536},
    }
    if tools:
        body["tools"] = [{"functionDeclarations": [t["schema"] for t in tools]}]
    data = _post("%s/%s:generateContent?key=%s" % (API_ROOT, model, api_key()), body)
    chunks, tool_calls = [], []
    candidate = (data.get("candidates") or [{}])[0]
    for part in candidate.get("content", {}).get("parts") or []:
        if part.get("thought"):
            continue  # reasoning traces are not transcript text; never surface them
        if "text" in part:
            chunks.append(part["text"])
        if "functionCall" in part:
            # Gemini 3 hands back an opaque thought signature per call and wants
            # it verbatim next turn, so it rides along with the call itself.
            tool_calls.append({"name": part["functionCall"].get("name", ""),
                               "args": part["functionCall"].get("args") or {},
                               "signature": part.get("thoughtSignature")})
    usage = data.get("usageMetadata") or {}
    return {"text": "".join(chunks).strip(), "tool_calls": tool_calls,
            "usage": {"input": usage.get("promptTokenCount", 0),
                      "output": usage.get("candidatesTokenCount", 0)}}


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


def _post(url, body, retries=5):
    """POST JSON, retrying transient failures; raise ``RuntimeError`` otherwise."""
    payload = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:  # subclass of URLError: catch first
            if error.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            detail = error.read()[:400].decode("utf-8", "replace")
            raise RuntimeError("Gemini HTTP %s: %s" % (error.code, detail)) from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError("Gemini unreachable: %s" % error) from error
