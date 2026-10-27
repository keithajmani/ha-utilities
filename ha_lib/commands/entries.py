"""Config entries (integrations) and HomeKit bridges."""
from ..config import HAError
from ..registry import command, restorer
from ..safety import Change, Plan, run


def find_entry(ctx, ref):
    entries = ctx.ha.ws("config_entries/get")
    hits = [e for e in entries if ref == e["entry_id"] or ref.lower() == (e.get("title") or "").lower()]
    if len(hits) != 1:
        raise HAError(f"{len(hits)} config entries match {ref!r}", "use the entry id from: ha.py entries --domain ...")
    return hits[0]


@command("entries", "config entries (integrations) and their state")
def entries(ctx):
    a = ctx.args
    kw = {"domain": a.domain} if a.domain else {}
    rows = []
    for e in ctx.ha.ws("config_entries/get", **kw):
        ignored = e.get("source") == "ignore"
        if ignored and not a.ignored:
            continue  # discoveries someone clicked Ignore on; not real integrations
        if a.problems and (e.get("state") == "loaded" or e.get("disabled_by")):
            continue  # disabled entries are deliberate, not problems
        if a.search and a.search.lower() not in f"{e.get('domain')} {e.get('title')}".lower():
            continue
        rows.append({"entry": e["entry_id"], "domain": e.get("domain"), "title": e.get("title"),
                     "state": e.get("state"), "disabled": e.get("disabled_by"), "ignored": "yes" if ignored else None,
                     "reason": e.get("reason")})
    rows.sort(key=lambda r: (r["domain"] or "", (r["title"] or "").lower()))
    ctx.out.rows(rows, ["entry", "domain", "title", "state", "disabled", "ignored", "reason"])


def _entries_args(p):
    p.add_argument("--domain", help="only this integration, e.g. hue")
    p.add_argument("--search", help="text in domain or title")
    p.add_argument("--problems", action="store_true", help="only enabled entries that are not loaded")
    p.add_argument("--ignored", action="store_true", help="include ignored discoveries (hidden by default)")


entries.args = _entries_args


def disabled_plan(ctx, entry_id, want_disabled, title="config entry"):
    e = find_entry(ctx, entry_id)
    now = e.get("disabled_by")
    target = "user" if want_disabled else None
    changes = [] if (now is not None) == want_disabled else [Change(f"{e['domain']} · {e['title']}", "disabled_by", now, target)]

    def apply():
        ctx.ha.ws("config_entries/disable", entry_id=e["entry_id"], disabled_by=target)

    def read_back():
        return {"entry_id": e["entry_id"], "disabled": find_entry(ctx, e["entry_id"]).get("disabled_by") is not None}

    def verify():
        got = read_back()["disabled"]
        return [] if got == want_disabled else [f"entry disabled={got}, wanted {want_disabled}"]

    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="config_entry_disabled", before={"entry_id": e["entry_id"], "disabled": now is not None},
                name=f"entry-{'disable' if want_disabled else 'enable'}",
                rollback=f"{'enable' if want_disabled else 'disable'} the entry again",
                detail=["HA reloads the integration; its entities go unavailable while disabled"] if want_disabled else [])


@command("entry disable", "disable an integration entry (entities go unavailable)", write=True)
def entry_disable(ctx):
    return run(ctx, disabled_plan(ctx, ctx.args.entry, True))


@command("entry enable", "enable a disabled integration entry", write=True)
def entry_enable(ctx):
    return run(ctx, disabled_plan(ctx, ctx.args.entry, False))


@command("entry reload", "reload an integration entry", write=True)
def entry_reload(ctx):
    e = find_entry(ctx, ctx.args.entry)

    def apply():
        ctx.ha.post(f"/api/config/config_entries/entry/{e['entry_id']}/reload")

    def verify():
        st = find_entry(ctx, e["entry_id"]).get("state")
        return [] if st == "loaded" else [f"state after reload is {st}"]

    return run(ctx, Plan(title="config entry", changes=[Change(f"{e['domain']} · {e['title']}", "reload", e.get("state"), "reloaded")],
                         apply=apply, verify=verify, name="entry-reload",
                         rollback="nothing to undo; reload again or restart HA if it fails to load"))


for _fn in (entry_disable, entry_enable, entry_reload):
    _fn.args = lambda p: p.add_argument("entry", help="config entry id, or exact title")


@restorer("config_entry_disabled")
def restore_entry(ctx, before):
    return disabled_plan(ctx, before["entry_id"], before["disabled"], title="restore config entry")


@command("homekit list", "HomeKit bridges: mode, filters, accessory count")
def homekit_list(ctx):
    rows = []
    for e in ctx.ha.ws("config_entries/get", domain="homekit"):
        row = {"bridge": e.get("title"), "state": e.get("state"), "entry": e["entry_id"]}
        if e.get("state") == "loaded":
            d = ctx.ha.get(f"/api/diagnostics/config_entry/{e['entry_id']}")
            opts = d.get("options", {}) if isinstance(d, dict) else {}
            filt = opts.get("filter", {})
            row.update({
                "mode": opts.get("mode"),
                "domains": ",".join(filt.get("include_domains", [])) or None,
                "entities": len(filt.get("include_entities", [])) or None,
                "excluded": len(filt.get("exclude_entities", [])) or None,
                "accessories": len(d.get("accessories", [])) if isinstance(d.get("accessories"), list) else None,
            })
        rows.append(row)
    rows.sort(key=lambda r: (r["bridge"] or "").lower())
    ctx.out.rows(rows, ["bridge", "state", "mode", "domains", "entities", "excluded", "accessories", "entry"])
