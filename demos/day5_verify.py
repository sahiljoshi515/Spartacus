"""Day 5 -- the check: grade the fleet's output without believing a word it said.

Concept this file teaches: an agent's final message is a claim, not evidence. It
will tell you the page has nine sections and 1,200 words because it intended to
write nine sections and 1,200 words. The only report worth reading is one
produced by counting the bytes on disk, which is what this does -- and it is
deliberately hostile: text inside <script> and <style> is not copy, an <svg>
without a <path> is not an illustration, and a test suite counts only if it
actually runs green.

Run from the repo root:  python3 demos/day5_verify.py
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "projects"
MIN_WORDS, MIN_SECTIONS, MIN_SVGS, MIN_INTERACTIONS = 1200, 9, 4, 3


def visible_words(html):
    """Count words a reader actually sees: no script, no style, no tags."""
    body = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return len([w for w in re.split(r"\s+", body) if re.search(r"[A-Za-z0-9]", w)])


def drawn_svgs(html):
    """Count inline SVGs that actually draw something, not empty or icon stubs."""
    return len([s for s in re.findall(r"(?is)<svg\b.*?</svg>", html)
                if re.search(r"(?i)<(path|polyline|polygon|circle|ellipse|rect)\b", s)])


def sections(html):
    """Count distinct page sections: <section>, plus header/footer landmarks."""
    return (len(re.findall(r"(?i)<section\b", html))
            + len(re.findall(r"(?i)<(header|footer)\b", html)))


def report(name, checks):
    """Print one project's checks and return True when every one of them passed."""
    ok = all(passed for passed, _ in checks.values())
    print("\n%-16s %s" % (name, "PASS" if ok else "FAIL"))
    for label, (passed, detail) in checks.items():
        print("   [%s] %-22s %s" % ("x" if passed else " ", label, detail))
    return ok


def grade(name):
    """Return ``{label: (passed, detail)}`` for one project, printing nothing.

    Split out from the printing so the fleet can read its own report card and
    hand the failures straight back to the agent that earned them.
    """
    return dict(CHECKS[name]())


def shortfall(name):
    """Return the failing checks for a project as ``"label: detail"`` lines."""
    return ["%s: %s" % (label, detail)
            for label, (passed, detail) in grade(name).items() if not passed]


def check_coffee():
    """Grade the roaster landing page against the design bar."""
    path = ROOT / "artisan-coffee" / "index.html"
    if not path.exists():
        return {"index.html exists": (False, "missing")}
    html = path.read_text(encoding="utf-8", errors="replace")
    low = html.lower()
    words, svgs, secs = visible_words(html), drawn_svgs(html), sections(html)
    interactions = sum(bool(re.search(p, low)) for p in
                       (r"addeventlistener", r"localstorage", r"classlist\.(toggle|add)"))
    return {
        "index.html exists": (True, "%d bytes" % len(html)),
        "visible words": (words > MIN_WORDS, "%d (need >%d)" % (words, MIN_WORDS)),
        "sections": (secs >= MIN_SECTIONS, "%d (need >=%d)" % (secs, MIN_SECTIONS)),
        "drawn inline SVGs": (svgs >= MIN_SVGS, "%d (need >=%d)" % (svgs, MIN_SVGS)),
        "interactions": (interactions >= MIN_INTERACTIONS,
                         "%d (need >=%d)" % (interactions, MIN_INTERACTIONS)),
        "localStorage": ("localstorage" in low, "dark-mode persistence"),
        "accordion": (bool(re.search(r"(?i)accordion|<details\b", html)), "FAQ"),
        "monthly/annual toggle": (bool(re.search(r"(?i)annual", html)), "subscription"),
        "brew-guide tabs": (bool(re.search(r"(?i)\btabs?\b", html)), "tab panels"),
        "css custom properties": (low.count("--") > 20, "%d '--' tokens" % low.count("--")),
        "responsive breakpoints": (len(re.findall(r"@media", low)) >= 2,
                                   "%d @media" % len(re.findall(r"@media", low))),
        "no lorem ipsum": ("lorem ipsum" not in low, "real copy"),
    }


def check_taskman():
    """Grade the CLI task manager, chiefly by running its own test suite."""
    workdir = ROOT / "taskman"
    checks = {}
    for name in ("taskman.py", "test_taskman.py", "README.md"):
        checks["%s exists" % name] = ((workdir / name).exists(), str(workdir / name))
    if not (workdir / "test_taskman.py").exists():
        return checks
    done = subprocess.run([sys.executable, "-m", "unittest", "test_taskman.py", "-v"],
                          cwd=workdir, capture_output=True, text=True, timeout=300)
    output = done.stdout + done.stderr
    cases = len(re.findall(r"\.\.\. ok", output))
    source = (workdir / "taskman.py").read_text(encoding="utf-8", errors="replace")
    checks["tests pass"] = (done.returncode == 0, output.strip().splitlines()[-1:] or [""])
    checks["10+ test cases"] = (cases >= 10, "%d passing" % cases)
    checks["subcommands"] = (all(('"%s"' % c in source or "'%s'" % c in source)
                                 for c in ("add", "list", "done", "rm", "stats")),
                             "add list done rm stats")
    checks["json persistence"] = ("json" in source.lower(), "json module")
    checks["subprocess tests"] = ("subprocess" in (workdir / "test_taskman.py")
                                  .read_text(encoding="utf-8", errors="replace"),
                                  "driven via subprocess")
    return checks


def check_viper():
    """Grade the snake game."""
    path = ROOT / "viper" / "index.html"
    if not path.exists():
        return {"index.html exists": (False, "missing")}
    html = path.read_text(encoding="utf-8", errors="replace")
    low = html.lower()
    return {
        "index.html exists": (True, "%d bytes" % len(html)),
        "requestAnimationFrame": ("requestanimationframe" in low, "game loop"),
        "canvas": ("<canvas" in low and "getcontext" in low, "2d context"),
        "localStorage": ("localstorage" in low, "high score"),
        "speed-up": (bool(re.search(r"(?i)speed|interval|delay", html)), "every 5 foods"),
        "pause": (bool(re.search(r"(?i)pause", html)), "pause/resume"),
        "restart": (bool(re.search(r"(?i)restart|new game", html)), "restart"),
        "keys": (bool(re.search(r"(?i)arrow(up|left)", html)), "arrows/WASD"),
        "drawn inline SVGs": (drawn_svgs(html) >= 1, "%d" % drawn_svgs(html)),
        "css custom properties": (low.count("--") > 10, "%d '--' tokens" % low.count("--")),
    }


CHECKS = {"artisan-coffee": check_coffee, "taskman": check_taskman,
          "viper": check_viper}


def main():
    """Grade every project and exit non-zero if any of them falls short."""
    results = [report(name, check()) for name, check in CHECKS.items()]
    print("\n%d/%d projects pass" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
