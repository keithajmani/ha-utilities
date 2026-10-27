"""Undo from a before-copy, and the audit trail."""
import json
import os
from datetime import datetime, timezone

from ..config import HAError
from ..registry import RESTORERS, command
from ..safety import run
from .states import parse_since


def _snapshot_path(ctx, ref):
    for p in (ref, ctx.s.path("snapshots", ref), ctx.s.path("snapshots", ref + ".json")):
        if os.path.isfile(p):
            return p
    raise HAError(f"no snapshot {ref!r}", "list them with: ha.py snapshots")


@command("restore", "put a before-copy back (same dry run and --yes rules as any write)", write=True)
def restore(ctx):
    path = _snapshot_path(ctx, ctx.args.snapshot)
    with open(path) as f:
        snap = json.load(f)
    fn = RESTORERS.get(snap.get("kind"))
    if not fn:
        raise HAError(f"snapshot kind {snap.get('kind')!r} has no restorer")
    plan = fn(ctx, snap["before"])
    plan.name = "restore-" + plan.name
    ctx.out.line(f"restoring {os.path.basename(path)} (from: {' '.join(snap.get('command', []))})")
    return run(ctx, plan)


restore.args = lambda p: p.add_argument("snapshot", help="snapshot file name, as printed after the change")


@command("snapshots", "recent before-copies, newest first")
def snapshots(ctx):
    d = ctx.s.path("snapshots")
    rows = []
    for name in sorted(os.listdir(d) if os.path.isdir(d) else [], reverse=True):
        try:
            with open(os.path.join(d, name)) as f:
                snap = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({"snapshot": name, "kind": snap.get("kind"), "when": ctx.out.time(snap.get("time")),
                     "command": " ".join(snap.get("command", []))[:90]})
    ctx.out.rows(rows, ["snapshot", "kind", "when", "command"])


@command("audit", "what ha.py did, newest first (writes only unless --reads)")
def audit_cmd(ctx):
    a = ctx.args
    since = parse_since(a.since, ctx.s.timezone)
    path = ctx.s.path("logs", "ha.log")
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = datetime.fromisoformat(e["time"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t < since or (e.get("result") == "read" and not a.reads):
                    continue
                rows.append({"when": ctx.out.time(e["time"], "%b %d %H:%M:%S"), "result": e.get("result"),
                             "command": " ".join(e.get("cmd", []))[:90], "plan": e.get("plan"), "snapshot": e.get("snapshot")})
    rows.reverse()
    ctx.out.rows(rows, ["when", "result", "command", "plan", "snapshot"])


def _audit_args(p):
    p.add_argument("--since", default="1d", help="30m, 6h, 2d or ISO time; default 1d")
    p.add_argument("--reads", action="store_true", help="include read commands")


audit_cmd.args = _audit_args
