"""Safety gate for writes: plan, plan id, before-copy, git checkpoints, apply, read-back, audit log."""
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .config import HAError

EXIT_REFUSED = 3


@dataclass
class Change:
    target: str
    field: str
    before: Any
    after: Any


@dataclass
class Plan:
    """What a write command will do.

    kind/before make the change restorable: `ha.py restore` hands `before` to the restorer
    registered for `kind`. A plan without a kind (a service call) has no automatic undo.
    """
    title: str
    changes: list
    apply: Callable[[], Any]
    rollback: str
    kind: Optional[str] = None
    before: Any = None
    verify: Optional[Callable[[], list]] = None  # returns a list of problems, empty when fine
    after: Optional[Callable[[], Any]] = None    # read-back saved next to the before-copy
    name: str = "change"                          # used in file names and commit messages
    detail: list = field(default_factory=list)    # extra plan lines (diff summary, warnings)


def plan_id(argv, plan):
    blob = json.dumps({"argv": argv, "before": plan.before, "changes": [c.__dict__ for c in plan.changes]},
                      sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:6]


def _fmt(v):
    if v is None:
        return "(none)"
    if isinstance(v, (dict, list)):
        s = json.dumps(v, separators=(",", ":"), default=str)
        return s if len(s) <= 100 else s[:97] + "..."
    return str(v)


def run(ctx, plan):
    """Print the plan; apply it only with --yes and a matching --plan id."""
    out = ctx.out
    if not plan.changes:
        out.line("no change needed: already as requested")
        audit(ctx, "no-op")
        return 0
    pid = plan_id(ctx.argv, plan)
    out.line(f"PLAN {pid}  {plan.title} · {len(plan.changes)} change{'s' if len(plan.changes) != 1 else ''}")
    for c in plan.changes:
        out.line(f"  {c.target}  {c.field}: {_fmt(c.before)} → {_fmt(c.after)}")
    for d in plan.detail:
        out.line(f"  {d}")
    undo = "ha.py restore <snapshot printed after apply>" if plan.kind else "no automatic undo"
    out.line(f"ROLLBACK  {plan.rollback}  ({undo})")

    if not ctx.yes:
        out.line(f"dry run, nothing changed. re-run with --yes --plan {pid} to apply")
        audit(ctx, "planned", plan=pid)
        return 0
    if ctx.plan_id != pid:
        audit(ctx, "refused", plan=pid, given=ctx.plan_id)
        raise HAError(f"plan id mismatch: this run plans {pid}, --plan said {ctx.plan_id}",
                      "the state or the command changed since the dry run; review the new plan above", EXIT_REFUSED)

    snap = None
    commits = []
    if plan.kind:
        snap = ctx.out.save(plan.name, {
            "kind": plan.kind, "command": ctx.argv, "plan": pid,
            "time": datetime.now(timezone.utc).isoformat(), "before": plan.before,
            "changes": [c.__dict__ for c in plan.changes],
        }, folder="snapshots")
        commits.append(git_commit(ctx, [snap], f"ha.py: {plan.name} (before)"))

    try:
        plan.apply()
    except Exception as e:
        audit(ctx, "error", plan=pid, snapshot=_rel(ctx, snap), error=str(e))
        raise

    problems = plan.verify() if plan.verify else []
    if snap and plan.after:
        with open(snap) as f:
            data = json.load(f)
        data["after"] = plan.after()
        with open(snap, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")
    result = "verify-failed" if problems else "applied"
    audit(ctx, result, plan=pid, snapshot=_rel(ctx, snap), problems=problems or None)
    if snap:
        commits.append(git_commit(ctx, [snap, ctx.s.path("logs", "ha.log")], f"ha.py: {plan.name} (after)"))

    commits = [c for c in commits if c]
    out.line("APPLIED" + (f"  commits {' '.join(commits)}" if commits else ""))
    if snap:
        out.line(f"UNDO  ha.py restore {os.path.basename(snap)}")
    if problems:
        for p in problems:
            out.line(f"VERIFY FAILED  {p}")
        return 1
    out.line("verified by read-back" if plan.verify else "done (this command has no read-back)")
    return 0


def _rel(ctx, path):
    return os.path.relpath(path, ctx.s.home) if path else None


def audit(ctx, result, **extra):
    d = ctx.s.path("logs")
    os.makedirs(d, exist_ok=True)
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cmd": ctx.argv, "result": result}
    entry.update({k: v for k, v in extra.items() if v is not None})
    with open(os.path.join(d, "ha.log"), "a") as f:
        f.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")


def git_commit(ctx, paths, message):
    """Commit only our own files, so unrelated work in the repo is never swept in."""
    home = ctx.s.home
    if not os.path.isdir(os.path.join(home, ".git")):
        return None
    rel = [os.path.relpath(p, home) for p in paths if p and os.path.exists(p)]
    try:
        subprocess.run(["git", "-C", home, "add", "--", *rel], check=True, capture_output=True)
        r = subprocess.run(["git", "-C", home, "commit", "-q", "-m", message, "--", *rel], capture_output=True, text=True)
        if r.returncode != 0:
            ctx.out.note(f"git commit skipped: {(r.stdout + r.stderr).strip()[:120]}")
            return None
        sha = subprocess.run(["git", "-C", home, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        return sha.stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        ctx.out.note(f"git commit failed: {e}")
        return None
