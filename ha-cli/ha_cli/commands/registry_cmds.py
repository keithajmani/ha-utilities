"""Entity, device and area registries, and voice assistant exposure."""
from ..config import HAError
from ..registry import command, restorer
from ..safety import Change, Plan, run

ASSISTANTS = {"alexa": "cloud.alexa", "assist": "conversation", "google": "cloud.google_assistant"}


def _clear(v):
    """'none' on the command line means clear the value."""
    return None if v is not None and v.lower() in ("none", "") else v


def _diff(current, desired):
    """current/desired: {key: {field: value}} -> (changes, before-subset)."""
    changes, before = [], {}
    for key, fields in desired.items():
        for f, val in fields.items():
            if current[key].get(f) != val:
                changes.append(Change(key, f, current[key].get(f), val))
                before.setdefault(key, {})[f] = current[key].get(f)
    return changes, before


# ---------- reads ----------

@command("areas", "list areas")
def areas(ctx):
    rows = [{"area": a["area_id"], "name": a["name"], "floor": a.get("floor_id")} for a in ctx.ha.areas()]
    ctx.out.rows(sorted(rows, key=lambda r: r["area"]), ["area", "name", "floor"])


@command("entities", "search the entity registry")
def entities(ctx):
    a = ctx.args
    area_names = {x["area_id"]: x["name"] for x in ctx.ha.areas()}
    dev_area = {d["id"]: d.get("area_id") for d in ctx.ha.ws("config/device_registry/list")}
    want_area = ctx.ha.resolve_area(a.area) if a.area else None
    rows = []
    for e in ctx.ha.ws("config/entity_registry/list"):
        eid = e["entity_id"]
        aid = e.get("area_id") or dev_area.get(e.get("device_id"))
        name = e.get("name") or e.get("original_name")
        if a.domain and not eid.startswith(a.domain + "."):
            continue
        if a.integration and e.get("platform") != a.integration:
            continue
        if a.area and aid != want_area:
            continue
        if a.search and a.search.lower() not in f"{eid} {name or ''}".lower():
            continue
        if not a.disabled and e.get("disabled_by"):
            continue
        rows.append({"entity": eid, "name": name, "area": area_names.get(aid, aid),
                     "own_area": "yes" if e.get("area_id") else None, "platform": e.get("platform"),
                     "disabled": e.get("disabled_by"), "hidden": e.get("hidden_by")})
    rows.sort(key=lambda r: r["entity"])
    ctx.out.rows(rows, ["entity", "name", "area", "own_area", "platform", "disabled", "hidden"])


def _entities_args(p):
    p.add_argument("--domain", help="only this domain, e.g. light")
    p.add_argument("--area", help="area id or name (entity's own or its device's)")
    p.add_argument("--integration", help="platform, e.g. alexa_devices")
    p.add_argument("--search", help="text in entity id or name")
    p.add_argument("--disabled", action="store_true", help="include disabled entities")


entities.args = _entities_args


@command("devices", "search the device registry")
def devices(ctx):
    a = ctx.args
    area_names = {x["area_id"]: x["name"] for x in ctx.ha.areas()}
    want_area = ctx.ha.resolve_area(a.area) if a.area else None
    rows = []
    for d in ctx.ha.ws("config/device_registry/list"):
        name = d.get("name_by_user") or d.get("name")
        if a.area and d.get("area_id") != want_area:
            continue
        if a.search and a.search.lower() not in f"{name} {d.get('manufacturer')} {d.get('model')}".lower():
            continue
        rows.append({"device": d["id"], "name": name, "area": area_names.get(d.get("area_id"), d.get("area_id")),
                     "maker": d.get("manufacturer"), "model": d.get("model"), "disabled": d.get("disabled_by")})
    rows.sort(key=lambda r: (r["name"] or "").lower())
    ctx.out.rows(rows, ["device", "name", "area", "maker", "model", "disabled"])


def _devices_args(p):
    p.add_argument("--area", help="area id or name")
    p.add_argument("--search", help="text in name, maker or model")


devices.args = _devices_args


@command("exposed", "entities exposed to voice assistants")
def exposed(ctx):
    a = ctx.args
    data = ctx.ha.ws("homeassistant/expose_entity/list")["exposed_entities"]
    want = ASSISTANTS[a.to] if a.to else None
    rows = []
    for eid, flags in sorted(data.items()):
        on = [k for k, name in ASSISTANTS.items() if flags.get(name)]
        if want and not flags.get(want):
            continue
        if a.search and a.search.lower() not in eid:
            continue
        if on:
            rows.append({"entity": eid, "exposed_to": ",".join(on)})
    ctx.out.rows(rows, ["entity", "exposed_to"])


def _exposed_args(p):
    p.add_argument("--to", choices=ASSISTANTS, help="only this assistant")
    p.add_argument("--search", help="text in the entity id")


exposed.args = _exposed_args


# ---------- entity set ----------

ENTITY_FIELDS = ("name", "area_id", "icon", "disabled_by", "hidden_by")


def entity_plan(ctx, desired, title="entity registry"):
    current = {}
    for eid in desired:
        e = ctx.ha.ws("config/entity_registry/get", entity_id=eid)
        current[eid] = {f: e.get(f) for f in ENTITY_FIELDS}
    changes, before = _diff(current, desired)

    def apply():
        for eid, fields in desired.items():
            todo = {f: v for f, v in fields.items() if current[eid].get(f) != v}
            if todo:
                ctx.ha.ws("config/entity_registry/update", entity_id=eid, **todo)

    def read_back():
        return {eid: {f: ctx.ha.ws("config/entity_registry/get", entity_id=eid).get(f) for f in fields}
                for eid, fields in desired.items()}

    def verify():
        got = read_back()
        return [f"{eid} {f} is {got[eid][f]!r}, wanted {v!r}" for eid, fs in desired.items() for f, v in fs.items() if got[eid][f] != v]

    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="entity_registry", before=before, name="entity-set",
                rollback="set the fields back to their before values")


@command("entity set", "rename, move area, icon, enable/disable or hide entities", write=True)
def entity_set(ctx):
    a = ctx.args
    fields = {}
    if a.name is not None:
        fields["name"] = _clear(a.name)
    if a.area is not None:
        fields["area_id"] = ctx.ha.resolve_area(a.area)
    if a.icon is not None:
        fields["icon"] = _clear(a.icon)
    if a.disable or a.enable:
        fields["disabled_by"] = "user" if a.disable else None
    if a.hide or a.unhide:
        fields["hidden_by"] = "user" if a.hide else None
    if not fields:
        raise HAError("nothing to change", "give --name, --area, --icon, --disable/--enable or --hide/--unhide", 2)
    return run(ctx, entity_plan(ctx, {eid: dict(fields) for eid in a.entity}))


def _entity_set_args(p):
    p.add_argument("entity", nargs="+", help="one or more entity ids")
    p.add_argument("--name", help="new name, or 'none' to inherit from the device")
    p.add_argument("--area", help="area id or name, or 'none' to use the device's area")
    p.add_argument("--icon", help="mdi:icon, or 'none'")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--disable", action="store_true", help="disable the entity")
    g.add_argument("--enable", action="store_true", help="enable the entity")
    h = p.add_mutually_exclusive_group()
    h.add_argument("--hide", action="store_true", help="hide from auto-generated dashboards")
    h.add_argument("--unhide", action="store_true", help="show again")


entity_set.args = _entity_set_args


@restorer("entity_registry")
def restore_entities(ctx, before):
    return entity_plan(ctx, before, title="restore entity registry")


# ---------- device set ----------

def _find_device(ctx, ref):
    devs = ctx.ha.ws("config/device_registry/list")
    hits = [d for d in devs if ref == d["id"] or ref.lower() in ((d.get("name_by_user") or "").lower(), (d.get("name") or "").lower())]
    if len(hits) != 1:
        raise HAError(f"{len(hits)} devices match {ref!r}", "use the device id from: ha.py devices --search ...")
    return hits[0]


def device_plan(ctx, desired, title="device registry"):
    devs = {d["id"]: d for d in ctx.ha.ws("config/device_registry/list")}
    current = {did: {f: devs[did].get(f) for f in ("name_by_user", "area_id")} for did in desired}
    changes, before = _diff(current, desired)
    for c in changes:
        c.target = f"{devs[c.target].get('name_by_user') or devs[c.target].get('name')} ({c.target[:8]})"

    def apply():
        for did, fields in desired.items():
            todo = {f: v for f, v in fields.items() if current[did].get(f) != v}
            if todo:
                ctx.ha.ws("config/device_registry/update", device_id=did, **todo)

    def read_back():
        now = {d["id"]: d for d in ctx.ha.ws("config/device_registry/list")}
        return {did: {f: now[did].get(f) for f in fields} for did, fields in desired.items()}

    def verify():
        got = read_back()
        return [f"{did} {f} is {got[did][f]!r}, wanted {v!r}" for did, fs in desired.items() for f, v in fs.items() if got[did][f] != v]

    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="device_registry", before=before, name="device-set",
                rollback="set name and area back to their before values")


@command("device set", "rename a device or move it to an area", write=True)
def device_set(ctx):
    a = ctx.args
    d = _find_device(ctx, a.device)
    fields = {}
    if a.name is not None:
        fields["name_by_user"] = _clear(a.name)
    if a.area is not None:
        fields["area_id"] = ctx.ha.resolve_area(a.area)
    if not fields:
        raise HAError("nothing to change", "give --name or --area", 2)
    return run(ctx, device_plan(ctx, {d["id"]: fields}))


def _device_set_args(p):
    p.add_argument("device", help="device id or exact name")
    p.add_argument("--name", help="new name, or 'none' for the integration's name")
    p.add_argument("--area", help="area id or name, or 'none'")


device_set.args = _device_set_args


@restorer("device_registry")
def restore_devices(ctx, before):
    return device_plan(ctx, before, title="restore device registry")


# ---------- expose ----------

def expose_plan(ctx, desired, title="voice exposure"):
    """desired: {entity_id: {assistant_key: bool}}"""
    data = ctx.ha.ws("homeassistant/expose_entity/list")["exposed_entities"]
    current = {eid: {k: bool(data.get(eid, {}).get(ASSISTANTS[k])) for k in fs} for eid, fs in desired.items()}
    changes, before = _diff(current, desired)

    def apply():
        groups = {}
        for c in changes:
            groups.setdefault((c.field, c.after), []).append(c.target)
        for (assistant, value), eids in groups.items():
            ctx.ha.ws("homeassistant/expose_entity", assistants=[ASSISTANTS[assistant]], entity_ids=eids, should_expose=value)

    def read_back():
        now = ctx.ha.ws("homeassistant/expose_entity/list")["exposed_entities"]
        return {eid: {k: bool(now.get(eid, {}).get(ASSISTANTS[k])) for k in fs} for eid, fs in desired.items()}

    def verify():
        got = read_back()
        return [f"{eid} {k} is {got[eid][k]}, wanted {v}" for eid, fs in desired.items() for k, v in fs.items() if got[eid][k] != v]

    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="expose", before=before, name="expose", rollback="expose or hide them again as before")


@command("expose", "expose or hide entities for Alexa, Assist or Google", write=True)
def expose(ctx):
    a = ctx.args
    to = [t.strip() for t in a.to.split(",")]
    bad = [t for t in to if t not in ASSISTANTS]
    if bad:
        raise HAError(f"unknown assistant {bad[0]!r}", f"use {', '.join(ASSISTANTS)}", 2)
    return run(ctx, expose_plan(ctx, {eid: {t: a.on for t in to} for eid in a.entity}))


def _expose_args(p):
    p.add_argument("entity", nargs="+", help="one or more entity ids")
    p.add_argument("--to", required=True, help="alexa, assist, google (comma list)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true", dest="on", help="expose")
    g.add_argument("--off", action="store_false", dest="on", help="hide")


expose.args = _expose_args


@restorer("expose")
def restore_expose(ctx, before):
    return expose_plan(ctx, before, title="restore voice exposure")
