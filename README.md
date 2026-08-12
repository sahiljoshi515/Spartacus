# spartacus

The smallest coding agent that is still a real one. Ten modules do the work, a
CLI and a fleet runner sit on top, and there are **zero dependencies** — no
framework, no SDK, not even `requests`. It talks to Gemini over `urllib` from
the standard library.

It is built to be read. Every file fits on a screen or two, every file explains
why it is shaped the way it is, and the whole thing was written one day at a
time so that each idea arrives on its own.

```
you: build me a snake game in one html file
  write_file path=index.html content=<!doctype html><html lang="en">…
  Wrote 14204 chars to index.html
  bash command=python3 -c "print(open('index.html').read().count('requestAnimationFrame'))"
  3
Done — index.html has grid movement on requestAnimationFrame, a score,
pause on space, and a high score in localStorage.
```

## Running it

One environment variable, and nothing else to install:

```sh
export SPARTACUS_API_KEY=...        # or GEMINI_API_KEY
export SPARTACUS_MODEL=...          # optional; overrides the built-in default
```

Three ways in:

```sh
# 1. headless: one task, then exit. Defaults to --mode yolo, because
#    there is nobody sitting there to approve anything.
python3 -m spartacus -p "add type hints to utils.py and run the tests" -d ./project

# 2. interactive: a prompt loop. Defaults to --mode safe, so every write
#    and every shell command asks you first.
python3 -m spartacus -d ./project

# 3. resume: pick up the newest session in that directory, including one
#    that died mid-tool-call.
python3 -m spartacus --resume -d ./project
```

Useful flags: `-m/--model` to override the model, `--mode {safe,yolo,read-only}`
to override the computed default, `--max-turns` to bound a run.

The working directory is a jail for the five file tools — `read_file`,
`write_file`, `edit_file`, `list_files` and `grep` all resolve paths and refuse
anything outside it. `bash` is not jailed, by construction; see the honest note
at the top of `security.py`.

## Anatomy, one day at a time

| Day | File | What it adds | The idea |
|---|---|---|---|
| 1 | `provider.py` | Gemini wire format, retries | One translation boundary; nothing else opens a socket |
| 1 | `loop.py` | think → act → observe → repeat | An agent is a while-loop around a stateless model |
| 2 | `tools.py` | `@tool`, six core tools, the path jail | A tool is one function; the schema is derived, never written twice |
| 2 | `security.py` | `Policy`: allow, refuse, or ask | Capability and permission are different questions |
| 3 | `context.py` | compaction against a token budget | The model summarises its own past when history gets heavy |
| 3 | `memory.py` | `Spartacus.md`, the system prompt | Durable memory is a markdown file a human can edit |
| 3 | `skills.py` | `skills/<name>/SKILL.md`, loaded on demand | Ten skills you might need beat one prompt you mostly don't |
| 4 | `session.py` | JSONL transcript, torn-tail repair | A killed process is a resumable one |
| 4 | `subagent.py` | `spawn_agent`, depth-capped | Delegation is a tool; the child's context is its own |
| 4 | `harness.py` | `Harness` — the object that wires it all | Composition, not logic |
| 5 | `cli.py` | headless and interactive front doors | The mode default is computed: ask when a human is there |
| 5 | `fleet.py` | `run_fleet` — many agents, one directory each | Agents wait on sockets; waiting parallelises |

Read them in that order and the whole system arrives in about an hour.

## Composing your own

`Harness` takes `extra_tools`, and a tool is one decorated function. The
decorator derives the schema the model reads from the signature you wrote, so
the two cannot drift apart:

```python
from spartacus import Harness, tool


@tool("Fetch the current price of a ticker in USD",
      ticker="Stock symbol, such as NVDA")
def stock_price(ticker):
    """Every parameter arrives as a string; coerce at the boundary."""
    return "%s: 184.22" % ticker.upper()


agent = Harness(
    workdir="./research",
    extra_tools=[stock_price],
    system_extra="Prefer tables to prose when reporting numbers.",
)
print(agent.run("Compare NVDA and AMD, and write the result to compare.md"))
```

The tool shows up in the model's tool list beside the built-in six, and a name
that collides with one of them wins — that is how you replace `bash` with a
sandboxed version of your own.

For many jobs at once, one working directory each:

```python
from spartacus import Harness, run_fleet

jobs = [
    {"name": "docs", "workdir": "./out/docs", "task": "Write README.md for the API."},
    {"name": "tests", "workdir": "./out/tests", "task": "Write pytest cases for utils.py."},
]
for result in run_fleet(jobs, lambda workdir: Harness(workdir), max_workers=4):
    print(result["name"], result["ok"], result["report"][:80])
```

Give every job its own directory. The harness has no lock, and two agents in
one directory share a session log, a memory file, and a set of files they will
both happily edit.

## What it is not

A speed bump is not a sandbox. `security.py`'s deny list catches the commands
people fat-finger, not an adversary — and `bash` can go anywhere the account
running it can go. Point spartacus at a directory you are willing to lose, or
give it a `Policy` that asks.
