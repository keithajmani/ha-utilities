"""UI helpers (toggle, number, text, dropdown, date/time, button, counter, timer, schedule): read and save."""
from ..config import HAError
from ..registry import command, restorer
from ..safety import Change, Plan, run
from .config_cmds import diff_detail, dump, load_file, _io_args

# Helpers stored by Home Assistant's helper collections, each with <type>/list|create|update|delete.
# Template, group, utility meter and other helpers made through an integration's setup screens are not here:
# they are config entries, and their options can't be saved and put back as one config.
TYPES = ("input_boolean", "input_button", "input_datetime", "input_number", "input_select", "input_text",
         "counter", "timer", "schedule")


def _domain(ref):
    d = ref.split(".", 1)[0]
    if d not in TYPES:
        raise HAError(f"{d!r} is not a helper type ha.py can save", "types: " + ", ".join(TYPES))
    return d


def _items(ctx, domain):
    return {i["id"]: i for i in ctx.ha.ws(f"{domain}/list")}


def _cfg(item):
    return None if item is None else {k: v for k, v in item.items() if k != "id"}


def _find(ctx, entity_id):
    """(type, id in its collection) for a UI helper's entity id, or None. The id is the registry's unique id."""
    domain = _domain(entity_id)
    try:
        e = ctx.ha.ws("config/entity_registry/get", entity_id=entity_id)
    except HAError:
        return None
    if not e or e.get("platform") != domain or e.get("unique_id") not in _items(ctx, domain):
        return None
    return domain, e["unique_id"]


def _item_id(ctx, entity_id):
    if "." not in entity_id:
        raise HAError(f"{entity_id!r} is a type, not a helper", f"give the entity id, e.g. {entity_id}.guest_mode")
    found = _find(ctx, entity_id)
    if not found:
        raise HAError(f"{entity_id} is not a UI helper", "only helpers made in Settings → Helpers can be saved (YAML ones can't)")
    return found


@command("helper list", "UI helpers with type and name")
def helper_list(ctx):
    types = [_domain(ctx.args.type)] if ctx.args.type else TYPES
    ents = {(e.get("platform"), e.get("unique_id")): e["entity_id"] for e in ctx.ha.ws("config/entity_registry/list")}
    rows = []
    for d in types:
        for iid, item in _items(ctx, d).items():
            name = item.get("name")
            if ctx.args.search and ctx.args.search.lower() not in f"{name} {iid}".lower():
                continue
            rows.append({"entity": ents.get((d, iid), f"{d}.? (id {iid})"), "type": d, "name": name, "icon": item.get("icon")})
    rows.sort(key=lambda r: r["entity"])
    ctx.out.rows(rows, ["entity", "type", "name", "icon"])


def _list_args(p):
    p.add_argument("--type", help="only this type, e.g. input_boolean")
    p.add_argument("--search", help="text in the name or id")


helper_list.args = _list_args


@command("helper get", "one UI helper's config")
def helper_get(ctx):
    domain, iid = _item_id(ctx, ctx.args.entity)
    dump(ctx, _cfg(_items(ctx, domain)[iid]), f"helper-{domain}-{iid}")


helper_get.args = lambda p: (p.add_argument("entity", help="helper entity id, e.g. input_boolean.guest_mode"), _io_args(p))


def helper_plan(ctx, domain, iid, new, title="helper"):
    """Save `new` as helper `iid` (iid None = create it), or remove helper `iid` when `new` is None."""
    items = _items(ctx, domain)
    cur = _cfg(items.get(iid)) if iid else None
    label = f"{domain} {iid or '(new)'}"
    state = {"id": iid}

    if new is None:  # undo of a create
        changes = [] if cur is None else [Change(label, "exists", True, False)]

        def apply():
            ctx.ha.ws(f"{domain}/delete", **{f"{domain}_id": iid})
    elif cur is None:
        if iid:
            raise HAError(f"{domain} {iid} no longer exists", "it was removed after the snapshot; make it again with helper save --create")
        changes = [Change(label, "config", "(new)", new.get("name") or "new")]

        def apply():
            state["id"] = ctx.ha.ws(f"{domain}/create", **new)["id"]
    else:
        # Home Assistant replaces the whole config on update, so a field left out of the file is removed.
        keys = list(new) + [k for k in cur if k not in new]
        changes = [Change(label, k, cur.get(k), new.get(k)) for k in keys if cur.get(k) != new.get(k)]

        def apply():
            ctx.ha.ws(f"{domain}/update", **{f"{domain}_id": iid}, **new)

    def read_back():
        return {"domain": domain, "id": state["id"], "config": _cfg(_items(ctx, domain).get(state["id"]))}

    def verify():
        got = read_back()["config"]
        if new is None:
            return [] if got is None else [f"{label} still exists"]
        if got is None:
            return [f"{label} not found after saving"]
        bad = [k for k, v in new.items() if got.get(k) != v]
        return [f"{label} read-back differs in: {', '.join(bad)}"] if bad else []

    detail = []
    if changes and new is not None and cur is None:
        detail = ["the new entity id is made from the name"]
    elif changes and new is not None and len(changes) > 3:
        detail = diff_detail(ctx, cur, new, f"helper-{domain}-{iid}")
    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="helper", before={"domain": domain, "id": iid, "config": cur}, name=f"helper-{domain}-{iid or 'new'}",
                rollback="remove it again" if cur is None and new is not None else
                ("make it again" if new is None else "save the before-copy of the helper back"),
                detail=detail)


@command("helper save", "save a UI helper from a JSON/YAML file", write=True)
def helper_save(ctx):
    a = ctx.args
    new = load_file(a.file)
    if not isinstance(new, dict) or not new.get("name"):
        raise HAError("file is not a helper config (no 'name')", "start from: ha.py helper get <entity> --yaml")
    new = {k: v for k, v in new.items() if k != "id"}
    if a.create:
        domain = _domain(a.target)
        if "." in a.target and _find(ctx, a.target):
            raise HAError(f"{a.target} already exists", "drop --create to change it")
        return run(ctx, helper_plan(ctx, domain, None, new))
    if "." not in a.target:
        raise HAError(f"{a.target!r} is a type, not a helper", "pass --create to make a new one")
    domain, iid = _item_id(ctx, a.target)
    return run(ctx, helper_plan(ctx, domain, iid, new))


def _save_args(p):
    p.add_argument("target", help="helper entity id; with --create, the type (e.g. input_boolean)")
    p.add_argument("--from", dest="file", required=True, help="JSON or YAML file")
    p.add_argument("--create", action="store_true", help="make a new helper")


helper_save.args = _save_args


@restorer("helper")
def restore_helper(ctx, before, after=None):
    domain, iid, cfg = before["domain"], before.get("id"), before.get("config")
    if cfg is None:  # it was created: remove the one that was made
        iid = iid or (after or {}).get("id")
        if not iid:
            raise HAError("this snapshot has no id for the helper it created", "remove it in Settings → Helpers")
        return helper_plan(ctx, domain, iid, None, title="restore helper")
    if iid not in _items(ctx, domain):  # it was removed: make it again (it gets a new id)
        return helper_plan(ctx, domain, None, cfg, title="restore helper")
    return helper_plan(ctx, domain, iid, cfg, title="restore helper")
