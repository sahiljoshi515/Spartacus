"""Day 5 -- the fleet: many agents at once, because one agent is a bottleneck.

Concept this file teaches: the slowest part of an agent is not thinking, it is
waiting -- for a socket, for a model, for a shell command to finish. Three
agents building three unrelated projects spend almost all of that wait in
parallel, and the wall-clock cost of the third project rounds to nothing. This
is threads rather than processes for exactly that reason: nothing here is
CPU-bound, so the GIL is released on every network read and never contended.

Design rules this file embodies:
  * One directory per job, and that is not a convention -- it is the isolation.
    Two agents sharing a working directory share a session log, a memory file,
    and a set of files they will both edit. The harness has no lock, so the
    only safe partition is the filesystem, and the caller draws it.
  * A job that raises is a result, not an exception. One agent hitting a 500 on
    its last turn must not discard the two that finished; the failure is
    recorded in the same shape as a success and the caller decides.
  * Results come back in input order. ``as_completed`` order is arrival order,
    which is a race -- and a report whose rows shuffle between runs is a report
    nobody can diff.
  * The harness is built inside the worker, not handed in. A ``Harness``
    carries a live message list, so one shared between threads is one
    transcript being written by three conversations at once.
"""

from concurrent.futures import ThreadPoolExecutor


def run_fleet(jobs, make_harness, max_workers=4):
    """Run ``jobs`` concurrently and return one result dict per job, in order.

    Each job is ``{"name", "workdir", "task"}``. Every result is
    ``{"name", "ok", "report"}`` -- the agent's final text when it finished,
    or ``"<type>: <message>"`` when it did not.
    """
    if not jobs:
        return []  # ThreadPoolExecutor rejects max_workers=0, and there is nothing to do
    with ThreadPoolExecutor(max_workers=min(max_workers, len(jobs))) as pool:
        # map, not submit/as_completed: it yields in input order for free.
        return list(pool.map(lambda job: _run_one(job, make_harness), jobs))


def _run_one(job, make_harness):
    """Run a single job to completion, turning any fault into a reported result."""
    try:
        agent = make_harness(job["workdir"])
        return {"name": job["name"], "ok": True, "report": agent.run(job["task"])}
    except Exception as error:  # deliberately broad: one job must not sink the fleet
        return {"name": job["name"], "ok": False,
                "report": "%s: %s" % (type(error).__name__, error)}
