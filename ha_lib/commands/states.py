"""States, history, templates and the system log."""
import fnmatch
import re
from datetime import datetime, timedelta, timezone

from ..config import HAError
from ..registry import command


def _match(pattern, value):
    return fnmatch.fnmatch(value, pattern) if any(ch in pattern for ch in "*?[") else value == pattern


def area_map(ha):
    """entity_id -> area name, using the entity's own area or else its device's."""
    areas = {a["area_id"]: a["name"] for a in ha.ws("config/area_registry/list")}
    dev_area = {d["id"]: d.get("area_id") for d in ha.ws("config/device_registry/list")}
    res = {}
    for e in ha.ws("config/entity_registry/list"):
        aid = e.get("area_id") or dev_area.get(e.get("device_id"))
        if aid:
            res[e["entity_id"]] = areas.get(aid, aid)
    return res


@command("state", "current state of entities (id or glob), one line each")
def state(ctx):
    a = ctx.args
    pats = a.entity
    if len(pats) == 1 and not any(ch in pats[0] for ch in "*?["):
        items = [ctx.ha.get(f"/api/states/{pats[0]}")]
    else:
        items = [s for s in ctx.ha.get("/api/states") if any(_match(p, s["entity_id"]) for p in pats)]
    items.sort(key=lambda s: s["entity_id"])
    areas = area_map(ctx.ha) if a.area else {}
    extra = a.attr.split(",") if a.attr else []
    rows = []
    for s in items:
        attrs = s.get("attributes", {})
        domain = s["entity_id"].split(".")[0]
        fields = extra or ctx.s.fields.get(domain, [])
        row = {"entity": s["entity_id"], "state": s["state"]}
        if a.area:
            row["area"] = areas.get(s["entity_id"])
        if a.name:
            row["name"] = attrs.get("friendly_name")
        for f in fields:
            row[f] = attrs.get(f)
        if a.changed:
            row["changed"] = ctx.out.time(s.get("last_changed"))
        rows.append(row)
    attr_cols = extra or list(dict.fromkeys(f for s in items for f in ctx.s.fields.get(s["entity_id"].split(".")[0], [])))
    cols = ["entity", "state"] + [c for c, on in (("area", a.area), ("name", a.name), ("changed", a.changed)) if on] + attr_cols
    ctx.out.rows(rows, cols)


def _state_args(p):
    p.add_argument("entity", nargs="+", help="entity id or glob, e.g. 'media_player.kitchen_*'")
    p.add_argument("--attr", help="comma list of attributes to show")
    p.add_argument("--area", action="store_true", help="show area")
    p.add_argument("--name", action="store_true", help="show friendly name")
    p.add_argument("--changed", action="store_true", help="show last changed time")


state.args = _state_args


def parse_since(value, tzname):
    """'30m', '6h', '2d' or an ISO time (local if no offset) -> aware UTC datetime."""
    m = re.fullmatch(r"(\d+)([mhd])", value)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
        return datetime.now(timezone.utc) - delta
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise HAError(f"bad time {value!r}", "use 30m, 6h, 2d or an ISO time")
    if dt.tzinfo is None and tzname:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo(tzname))
    return dt.astimezone(timezone.utc)  # a naive time is read as local time


@command("history", "state changes for entities over a period (local times)")
def history(ctx):
    a = ctx.args
    start = parse_since(a.since, ctx.s.timezone)
    params = {"filter_entity_id": ",".join(a.entity), "minimal_response": "", "no_attributes": ""}
    if a.until:
        params["end_time"] = parse_since(a.until, ctx.s.timezone).isoformat()
    data = ctx.ha.get(f"/api/history/period/{start.isoformat()}", params=params) or []
    rows = []
    for series in data:
        eid = series[0].get("entity_id") if series else None
        for i, s in enumerate(series):
            if i == 0 and not a.include_start:
                continue  # the first row is the state at the start of the window, not a change
            rows.append({"ts": s.get("last_changed") or "", "entity": s.get("entity_id", eid), "state": s.get("state")})
    rows.sort(key=lambda r: r["ts"])
    for r in rows:
        r["time"] = ctx.out.time(r.pop("ts"), "%b %d %H:%M:%S")
    ctx.out.rows(rows, ["time", "entity", "state"] if len(a.entity) > 1 else ["time", "state"],
                 note=None if rows else f"no changes since {ctx.out.time(start.isoformat())}")


def _history_args(p):
    p.add_argument("entity", nargs="+", help="one or more entity ids")
    p.add_argument("--since", default="6h", help="30m, 6h, 2d or ISO time (local); default 6h")
    p.add_argument("--until", help="end of window, same format")
    p.add_argument("--include-start", action="store_true", help="also show the state at the start of the window")


history.args = _history_args


@command("template", "evaluate a Jinja template in HA")
def template(ctx):
    ctx.out.line(ctx.ha.rest("POST", "/api/template", body={"template": ctx.args.template}, raw=True))


template.args = lambda p: p.add_argument("template", help="Jinja template, quoted")


@command("logs", "system log entries (warnings and errors), newest first")
def logs(ctx):
    a = ctx.args
    entries = ctx.ha.ws("system_log/list")
    rows = []
    for e in entries:
        msg = " | ".join(e.get("message") or [])
        if a.grep and a.grep.lower() not in (msg + " " + e.get("name", "")).lower():
            continue
        if a.level and e.get("level", "").lower() != a.level.lower():
            continue
        rows.append({"ts": e.get("timestamp") or 0, "level": e.get("level"), "source": e.get("name"),
                     "count": e.get("count"), "message": msg[:160]})
    rows.sort(key=lambda r: r["ts"], reverse=True)
    for r in rows:
        r["last"] = ctx.out.time(r.pop("ts"))
    ctx.out.rows(rows, ["last", "level", "source", "count", "message"])


def _logs_args(p):
    p.add_argument("--grep", help="text to match in message or logger name")
    p.add_argument("--level", help="WARNING, ERROR, CRITICAL")


logs.args = _logs_args
