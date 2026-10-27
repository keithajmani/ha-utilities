"""Dashboards (lovelace), automations and scripts: read, and save with diff + before-copy."""
import difflib
import json
import os

from ..config import HAError
from ..registry import command, restorer
from ..safety import Change, Plan, run

DIFF_LINES = 30


def load_file(path):
    if not os.path.exists(path):
        raise HAError(f"no file {path}")
    with open(path) as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError:
            raise HAError("PyYAML missing for a .yaml file", "use JSON, or install PyYAML in the venv: .venv/bin/pip install pyyaml")
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise HAError(f"{path} is not valid JSON", str(e))


def dump(ctx, obj, name):
    """Print as YAML when asked, else compact JSON (spilled to a file when big)."""
    if getattr(ctx.args, "yaml", False):
        try:
            import yaml
        except ImportError:
            raise HAError("PyYAML missing", "install PyYAML in the venv: .venv/bin/pip install pyyaml")
        ctx.out.line(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True).rstrip())
    elif getattr(ctx.args, "out", None):
        with open(ctx.args.out, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        ctx.out.line(f"saved {ctx.args.out}")
    else:
        ctx.out.obj(obj, name=name)


def diff_detail(ctx, before, after, name):
    a = json.dumps(before, indent=2, sort_keys=True).splitlines()
    b = json.dumps(after, indent=2, sort_keys=True).splitlines()
    diff = list(difflib.unified_diff(a, b, "before", "after", lineterm="", n=1))
    if not diff:
        return []
    path = ctx.out.save(f"{name}-diff", {"diff": diff})
    adds = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
    dels = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
    lines = [f"diff: +{adds} -{dels} lines (full diff {path})"]
    body = [d for d in diff[2:] if not d.startswith("@@")]
    lines += ["  " + d[:140] for d in body[:DIFF_LINES]]
    if len(body) > DIFF_LINES:
        lines.append(f"  ... {len(body) - DIFF_LINES} more lines in the file")
    return lines


def _io_args(p):
    p.add_argument("--yaml", action="store_true", help="print as YAML")
    p.add_argument("--out", help="save JSON to this file")


# ---------- dashboards ----------

def _dash_path(path):
    return None if path in ("lovelace", "default", "overview") else path


def count_cards(cfg):
    def walk(o):
        if isinstance(o, dict):
            return (1 if "type" in o and o is not cfg else 0) + sum(walk(v) for v in o.values())
        if isinstance(o, list):
            return sum(walk(v) for v in o)
        return 0
    views = cfg.get("views", []) if isinstance(cfg, dict) else []
    return f"{len(views)} views, {sum(walk(v.get('cards', [])) + walk(v.get('sections', [])) for v in views)} cards"


@command("dashboard list", "dashboards with url path and mode")
def dashboard_list(ctx):
    rows = [{"path": "lovelace", "title": "Overview (default)", "mode": None}]
    for d in ctx.ha.ws("lovelace/dashboards/list"):
        rows.append({"path": d.get("url_path"), "title": d.get("title"), "mode": d.get("mode"),
                     "admin": "yes" if d.get("require_admin") else None,
                     "protected": "yes" if d.get("url_path") in ctx.s.protected_dashboards else None})
    ctx.out.rows(rows, ["path", "title", "mode", "admin", "protected"])


def _pick_view(cfg, ref):
    for i, v in enumerate(cfg.get("views", [])):
        if ref in (str(i), v.get("path"), v.get("title")):
            return i, v
    raise HAError(f"no view {ref!r}", "views: " + ", ".join(str(v.get("path") or v.get("title") or i) for i, v in enumerate(cfg.get("views", []))))


@command("dashboard get", "one dashboard's config, or one view of it")
def dashboard_get(ctx):
    cfg = ctx.ha.ws("lovelace/config", url_path=_dash_path(ctx.args.path))
    name = ctx.args.path
    if ctx.args.view is not None:
        cfg = _pick_view(cfg, ctx.args.view)[1]
        name += f"-{ctx.args.view}"
    dump(ctx, cfg, name)


def _dash_get_args(p):
    p.add_argument("path", help="url path, e.g. dashboard-media (lovelace = Overview)")
    p.add_argument("--view", help="view path, title or index")
    _io_args(p)


dashboard_get.args = _dash_get_args


def dashboard_plan(ctx, path, new_cfg, title="dashboard"):
    url = _dash_path(path)
    cur = ctx.ha.ws("lovelace/config", url_path=url)
    changes = [] if cur == new_cfg else [Change(path, "config", count_cards(cur), count_cards(new_cfg))]

    def apply():
        ctx.ha.ws("lovelace/config/save", url_path=url, config=new_cfg)

    def read_back():
        return ctx.ha.ws("lovelace/config", url_path=url)

    def verify():
        return [] if read_back() == new_cfg else ["saved config differs from what was sent"]

    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="lovelace", before={"path": path, "config": cur}, name=f"dashboard-{path}",
                rollback="save the before-copy of the dashboard back",
                detail=diff_detail(ctx, cur, new_cfg, f"dashboard-{path}") if changes else [])


@command("dashboard save", "save a dashboard (or one view) from a JSON/YAML file", write=True)
def dashboard_save(ctx):
    a = ctx.args
    if a.path in ctx.s.protected_dashboards and not a.unprotect:
        raise HAError(f"dashboard {a.path} is protected in ha.toml", "pass --unprotect only if you really mean to overwrite it", 3)
    new = load_file(a.file)
    if a.view is not None:
        full = ctx.ha.ws("lovelace/config", url_path=_dash_path(a.path))
        i, _ = _pick_view(full, a.view)
        full = json.loads(json.dumps(full))
        full["views"][i] = new
        new = full
    if not isinstance(new, dict) or "views" not in new:
        raise HAError("file is not a dashboard config (no 'views')", "use --view to replace a single view")
    return run(ctx, dashboard_plan(ctx, a.path, new))


def _dash_save_args(p):
    p.add_argument("path", help="url path (lovelace = Overview)")
    p.add_argument("--from", dest="file", required=True, help="JSON or YAML file")
    p.add_argument("--view", help="replace only this view (path, title or index) with the file")
    p.add_argument("--unprotect", action="store_true", help="allow saving a protected dashboard")


dashboard_save.args = _dash_save_args


@restorer("lovelace")
def restore_dashboard(ctx, before):
    return dashboard_plan(ctx, before["path"], before["config"], title="restore dashboard")


# ---------- automations and scripts ----------

KINDS = {
    "automation": {"api": "/api/config/automation/config/", "domain": "automation"},
    "script": {"api": "/api/config/script/config/", "domain": "script"},
}


def _config_id(ctx, kind, ref):
    """automation: the automation's id (from entity attributes if an entity id is given). script: object id."""
    if kind == "automation":
        if ref.startswith("automation."):
            st = ctx.ha.get(f"/api/states/{ref}")
            cid = st.get("attributes", {}).get("id")
            if not cid:
                raise HAError(f"{ref} has no id attribute", "it is not UI-managed (YAML-only automations cannot be saved)")
            return cid
        return ref
    return ref.split(".", 1)[1] if ref.startswith("script.") else ref


def _read_config(ctx, kind, cid):
    try:
        return ctx.ha.get(KINDS[kind]["api"] + cid)
    except HAError as e:
        if str(e).startswith("404"):
            return None
        raise


def config_plan(ctx, kind, cid, new, title=None):
    cur = _read_config(ctx, kind, cid)
    api = KINDS[kind]["api"] + cid
    label = f"{kind} {cid}"
    if new is None:  # restore of something we created
        changes = [] if cur is None else [Change(label, "exists", True, False)]

        def apply():
            ctx.ha.rest("DELETE", api)
    else:
        changes = [] if cur == new else [Change(label, "config", "(new)" if cur is None else (cur.get("alias") or "existing"),
                                                new.get("alias") or "updated")]

        def apply():
            ctx.ha.post(api, body=new)  # HA reloads automations/scripts after a config save

    def read_back():
        return _read_config(ctx, kind, cid)

    def verify():
        got = read_back()
        if new is None:
            return [] if got is None else [f"{label} still exists"]
        missing = [k for k, v in new.items() if got is None or got.get(k) != v]
        return [f"{label} read-back differs in: {', '.join(missing)}"] if missing else []

    detail = diff_detail(ctx, cur or {}, new or {}, f"{kind}-{cid}") if changes else []
    return Plan(title=title or kind, changes=changes, apply=apply, verify=verify, after=read_back,
                kind=f"{kind}_config", before={"id": cid, "config": cur}, name=f"{kind}-{cid}",
                rollback="delete it again" if cur is None else f"save the before-copy of the {kind} back",
                detail=detail)


def _make_get(kind):
    def fn(ctx):
        cid = _config_id(ctx, kind, ctx.args.target)
        cfg = _read_config(ctx, kind, cid)
        if cfg is None:
            raise HAError(f"no {kind} with id {cid}")
        dump(ctx, cfg, f"{kind}-{cid}")
    return fn


def _make_save(kind):
    def fn(ctx):
        a = ctx.args
        cid = _config_id(ctx, kind, a.target)
        new = load_file(a.file)
        if _read_config(ctx, kind, cid) is None and not a.create:
            raise HAError(f"no {kind} with id {cid}", "pass --create to make a new one")
        return run(ctx, config_plan(ctx, kind, cid, new))
    return fn


for _kind in KINDS:
    _get = command(f"{_kind} get", f"read one {_kind}'s config")(_make_get(_kind))
    _get.args = lambda p, k=_kind: (p.add_argument("target", help=f"{k} entity id or config id"), _io_args(p))
    _save = command(f"{_kind} save", f"save one {_kind} from a JSON/YAML file (HA reloads it)", write=True)(_make_save(_kind))
    _save.args = lambda p, k=_kind: (p.add_argument("target", help=f"{k} entity id or config id"),
                                      p.add_argument("--from", dest="file", required=True, help="JSON or YAML file"),
                                      p.add_argument("--create", action="store_true", help=f"allow creating a new {k}"))

    def _restore(ctx, before, k=_kind):
        return config_plan(ctx, k, before["id"], before["config"], title=f"restore {k}")

    restorer(f"{_kind}_config")(_restore)
