"""The model registry: which vendor owns a name, and where its key comes from.

Concept this file teaches: "which model" and "how to talk to it" are different
questions, and mixing them is how a harness ends up with vendor names threaded
through ten files. This one answers only the first: given ``claude-sonnet-5`` or
the alias ``sonnet``, it says *anthropic*, and it says which environment
variable holds the credential. It opens no sockets and knows no wire formats --
that is ``provider.py``'s single job, and it stays single.

Design rules this file embodies:
  * Routing is by prefix, not by an enumerated list of every model id. Vendors
    ship new models weekly; a harness that needs editing to reach one released
    this morning is a harness that is always slightly out of date.
  * Aliases are a convenience over the real ids, never a replacement. ``sonnet``
    resolves to a full id which is what gets sent and what gets printed, so the
    transcript always records exactly which model answered.
  * An unknown prefix is an error with the list attached. "Unknown model" sends
    someone to the source; "unknown model, here are the prefixes I route" ends
    the question.
"""

import os

from . import config

DEFAULT_MODEL = "gemini-3.1-flash-lite"

# Per vendor: where the key lives, what the API root is, and the output cap the
# request must carry. Anthropic *requires* max_tokens; OpenAI infers it; Gemini
# takes a large one happily.
PROVIDERS = {
    "gemini": {
        "keys": ("SPARTACUS_API_KEY", "GEMINI_API_KEY"),
        "base": "https://generativelanguage.googleapis.com/v1beta",
        "max_output": 65536,
    },
    "openai": {
        "keys": ("OPENAI_API_KEY",),
        "base": "https://api.openai.com/v1",
        "max_output": None,
    },
    "anthropic": {
        "keys": ("ANTHROPIC_API_KEY",),
        "base": "https://api.anthropic.com/v1",
        "max_output": 16384,
    },
}

# Longest prefix wins, so "gpt-" and a future "gpt-oss-local" can diverge.
PREFIXES = {
    "gemini": "gemini",
    "gemma": "gemini",  # served by the same endpoint and the same key
    "learnlm": "gemini",
    "gpt": "openai",
    "chatgpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "claude": "anthropic",
}

# Short names for the ones typed most often. The value is always a real id.
ALIASES = {
    "flash-lite": "gemini-3.1-flash-lite",
    "flash": "gemini-3.5-flash",
    "gemini": "gemini-3.1-flash-lite",
    "pro": "gemini-3.1-pro-preview",
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5-20251001",
    "fable": "claude-fable-5",
}


def resolve(name):
    """Return ``(model_id, provider)`` for a model name, alias, or ``vendor:model``.

    The explicit form is the escape hatch. Prefix routing covers what exists
    today; ``openai:whatever-ships-next-week`` covers what does not, without
    anyone having to edit this file to try a new model once.
    """
    name = name.strip()
    vendor, sep, rest = name.partition(":")
    if sep and vendor in PROVIDERS:
        return rest.strip(), vendor
    model = ALIASES.get(name.lower(), name)
    return model, provider_of(model)


def provider_of(model):
    """Return the vendor that owns ``model``, or raise naming what is routable."""
    lowered = model.lower()
    for prefix in sorted(PREFIXES, key=len, reverse=True):
        if lowered.startswith(prefix):
            return PREFIXES[prefix]
    raise ValueError(
        "Unknown model %r. Routable prefixes: %s. Aliases: %s."
        % (model, ", ".join(sorted(PREFIXES)), ", ".join(sorted(ALIASES))))


def settings(provider):
    """Return the registry entry for a provider."""
    return PROVIDERS[provider]


def configured():
    """Return the providers that currently have a key available."""
    config.load()
    return sorted(name for name, spec in PROVIDERS.items()
                  if any(os.environ.get(key) for key in spec["keys"]))
