"""Automation and script traces: what ran, why it stopped, and each step's result."""
import json

from ..config import HAError
from ..registry import command
from .config_cmds import config_id, dump

# A trace path's first part is singular ("action/0"); configs use the plural key (or the old singular one).
_ROOT_KEYS = {"trigger": ("triggers", "trigger"), "condition": ("conditions", "condition"),
              "action": ("actions", "action"), "sequence": ("sequence",)}


def _list(ctx, kind, item_id):
    runs = ctx.ha.ws("trace/list", domain=kind, item_id=item_id) or []
    runs.sort(key=lambda r: (r.get("timestamp") or {}).get("start") or "", reverse=True)
    return runs


def _result(run):
    """One word for how a run ended."""
    if run.get("state") == "running":
        return "running"
    return run.get("script_execution") or run.get("state") or "-"


@command("automation traces", "an automation's recent runs, newest first: result, trigger, last step")
def automation_traces(ctx):
    return _traces(ctx, "automation")


@command("script traces", "a script's recent runs, newest first: result, last step")
def script_traces(ctx):
    return _traces(ctx, "script")


def _traces(ctx, kind):
    item_id = config_id(ctx, kind, ctx.args.target)
    rows = []
    for i, r in enumerate(_list(ctx, kind, item_id), 1):
        rows.append({"n": i, "time": ctx.out.time((r.get("timestamp") or {}).get("start"), "%b %d %H:%M:%S"),
                     "result": _result(r), "trigger": r.get("trigger"), "step": r.get("last_step"),
                     "error": r.get("error"), "run": r.get("run_id")})
    ctx.out.rows(rows, ["n", "time", "result", "trigger", "step", "error", "run"],
                 note=None if rows else f"no stored traces for {kind} {item_id} (Home Assistant keeps the last 5 by default)")


def _node(config, path):
    """The config item a trace path points at, or None."""
    parts = path.split("/")
    keys = _ROOT_KEYS.get(parts[0], (parts[0],))
    node = next((config[k] for k in keys if isinstance(config, dict) and k in config), None)
    for p in parts[1:]:
        if node is None:
            return None
        if isinstance(node, list):
            if p.isdigit():
                node = node[int(p)] if int(p) < len(node) else None
            # a word after a list ("if/condition/0") names the list itself: keep it
        elif isinstance(node, dict):
            if p.isdigit():
                node = node if p == "0" else None  # a single item written without a list
            else:
                node = node.get(p, next((node[k] for k in _ROOT_KEYS.get(p, ()) if k in node), None))
        else:
            return None
    if isinstance(node, list) and len(node) == 1:
        node = node[0]
    return node if isinstance(node, dict) else None


def _describe(node):
    """A short label for a trigger, condition or action config."""
    if not node:
        return None
    if node.get("alias"):
        return node["alias"]
    for key in ("action", "service"):
        if isinstance(node.get(key), str):
            return node[key]
    for key in ("trigger", "platform", "condition"):
        if isinstance(node.get(key), str):
            ent = node.get("entity_id")
            ent = ",".join(ent) if isinstance(ent, list) else ent
            return f"{key}={node[key]}" + (f" {ent}" if ent else "")
    for key in ("choose", "if", "repeat", "parallel", "sequence", "delay", "wait_template", "wait_for_trigger",
                "variables", "stop", "event", "scene", "device_id"):
        if key in node:
            return key
    return next(iter(node), None)


def _step_result(path, step):
    """One short value for what a step did."""
    r = step.get("result") or {}
    if path.startswith("trigger"):
        trig = (step.get("changed_variables") or {}).get("trigger") or {}
        return trig.get("description") or "triggered"
    if r.get("enabled") is False:
        return "disabled"
    if "result" in r:
        return "true" if r["result"] else "false"
    if "choice" in r:
        return f"choice {r['choice']}" if r["choice"] != "default" else "default"
    if "wait" in r:
        w = r["wait"] or {}
        return "wait timed out" if w.get("remaining") == 0 or w.get("timeout") else "wait done"
    if "delay" in r:
        return f"delay {r['delay']}" + (" done" if r.get("done") else "")
    if "stop" in r:
        return f"stop: {r['stop']}"
    if "params" in r:
        p = r["params"] or {}
        return f"called {p.get('domain')}.{p.get('service')}" if p.get("domain") else "called"
    if r:
        s = json.dumps(r, separators=(",", ":"), default=str)
        return s if len(s) <= 60 else s[:57] + "..."
    return None


@command("automation trace", "one automation run step by step: trigger, conditions, actions, errors")
def automation_trace(ctx):
    return _trace(ctx, "automation")


@command("script trace", "one script run step by step: actions and errors")
def script_trace(ctx):
    return _trace(ctx, "script")


def _trace(ctx, kind):
    a = ctx.args
    item_id = config_id(ctx, kind, a.target)
    runs = _list(ctx, kind, item_id)
    if not runs:
        raise HAError(f"no stored traces for {kind} {item_id}", "it has not run since Home Assistant started, or its traces were cleared")
    ref = a.run or "1"
    if ref.isdigit() and int(ref) <= len(runs):
        run = runs[int(ref) - 1]
    else:
        run = next((r for r in runs if r.get("run_id") == ref), None)
        if run is None:
            raise HAError(f"no run {ref!r}", f"use 1 to {len(runs)} (1 = newest) or a run id from: ha.py {kind} traces {a.target}")
    t = ctx.ha.ws("trace/get", domain=kind, item_id=item_id, run_id=run["run_id"])
    if a.out or a.yaml:
        return dump(ctx, t, f"{kind}-{item_id}-trace")
    if ctx.out.as_json:
        return ctx.out.obj(t, name=f"{kind}-{item_id}-trace")
    ts = t.get("timestamp") or run.get("timestamp") or {}
    head = [f"run {run['run_id']}", ctx.out.time(ts.get("start"), "%b %d %H:%M:%S"), _result(t or run)]
    if t.get("trigger") or run.get("trigger"):
        head.append(f"trigger={json.dumps(t.get('trigger') or run.get('trigger'))}")
    ctx.out.line("  ".join(head))
    config = t.get("config") or {}
    rows = []
    for path, steps in (t.get("trace") or {}).items():
        for step in steps:
            rows.append({"step": path, "time": ctx.out.time(step.get("timestamp"), "%H:%M:%S"),
                         "what": _describe(_node(config, path)), "result": _step_result(path, step),
                         "error": step.get("error")})
    ctx.out.rows(rows, ["step", "time", "what", "result", "error"])
    if t.get("error"):
        ctx.out.line(f"ERROR  {t['error']}")
    return 0


def _traces_args(kind):
    def add(p):
        p.add_argument("target", help=f"{kind} entity id or {'config' if kind == 'automation' else 'object'} id")
    return add


def _trace_args(kind):
    def add(p):
        p.add_argument("target", help=f"{kind} entity id or {'config' if kind == 'automation' else 'object'} id")
        p.add_argument("--run", help="1 = newest (default), 2 = the one before, or a run id")
        p.add_argument("--yaml", action="store_true", help="print the whole trace as YAML")
        p.add_argument("--out", help="save the whole trace as JSON to this file")
    return add


automation_traces.args = _traces_args("automation")
script_traces.args = _traces_args("script")
automation_trace.args = _trace_args("automation")
script_trace.args = _trace_args("script")
