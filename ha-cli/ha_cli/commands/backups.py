"""Backups: list, settings, and settings changes. Deleting backups is left out on purpose (do it in the HA UI)."""
from ..config import HAError
from ..registry import command, restorer
from ..safety import Change, Plan, run


def _gb(n):
    return f"{n / 1e9:.2f} GB" if n else None


@command("backups", "backups and where each copy is stored")
def backups(ctx):
    info = ctx.ha.ws("backup/info")
    rows = []
    for b in info.get("backups", []):
        agents = b.get("agents") or {a: {} for a in b.get("agent_ids", [])}
        size = b.get("size") or max([v.get("size") or 0 for v in agents.values()] + [0])
        rows.append({"ts": b.get("date") or "", "name": b.get("name"), "size": _gb(size),
                     "locations": ",".join(sorted(agents)), "auto": "yes" if b.get("with_automatic_settings") else None,
                     "id": b.get("backup_id")})
    rows.sort(key=lambda r: r["ts"], reverse=True)
    for r in rows:
        r["date"] = ctx.out.time(r.pop("ts"))
    note = None
    if info.get("last_completed_automatic_backup"):
        note = (f"last automatic {ctx.out.time(info['last_completed_automatic_backup'])} · "
                f"next {ctx.out.time(info.get('next_automatic_backup'))}")
    ctx.out.rows(rows, ["date", "name", "size", "locations", "auto", "id"], note=note)


def _settings(ctx):
    cfg = ctx.ha.ws("backup/config/info")["config"]
    cb = cfg.get("create_backup", {})
    return {
        "copies": cfg.get("retention", {}).get("copies"),
        "days": cfg.get("retention", {}).get("days"),
        "recurrence": cfg.get("schedule", {}).get("recurrence"),
        "time": cfg.get("schedule", {}).get("time"),
        "weekdays": cfg.get("schedule", {}).get("days"),
        "agents": sorted(cb.get("agent_ids", [])),
    }, cfg


@command("backup config", "automatic backup settings (encryption key redacted)")
def backup_config(ctx):
    flat, cfg = _settings(ctx)
    cb = cfg.get("create_backup", {})
    flat.update({"database": cb.get("include_database"), "all_addons": cb.get("include_all_addons"),
                 "addons": cb.get("include_addons"), "folders": cb.get("include_folders"),
                 "encryption_key": cb.get("password") or None})  # prints «redacted» when set
    ctx.out.obj({k: v for k, v in flat.items() if v not in (None, [])}, name="backup-config")


def _payload(fields):
    p = {}
    if "copies" in fields or "days" in fields:
        p["retention"] = {k: fields.get(k) for k in ("copies", "days") if k in fields}
    if "recurrence" in fields or "time" in fields or "weekdays" in fields:
        p["schedule"] = {}
        if "recurrence" in fields:
            p["schedule"]["recurrence"] = fields["recurrence"]
        if "time" in fields:
            p["schedule"]["time"] = fields["time"]
        if "weekdays" in fields:
            p["schedule"]["days"] = fields["weekdays"]
    if "agents" in fields:
        p["create_backup"] = {"agent_ids": fields["agents"]}
    return p


def backup_plan(ctx, desired, title="backup settings"):
    cur, _ = _settings(ctx)
    changes = [Change("backup", k, cur.get(k), v) for k, v in desired.items() if cur.get(k) != v]
    before = {c.field: c.before for c in changes}

    def apply():
        # retention needs both keys; keep the other one as it is
        p = _payload({k: v for k, v in desired.items() if cur.get(k) != v})
        if "retention" in p:
            p["retention"] = {"copies": desired.get("copies", cur["copies"]), "days": desired.get("days", cur["days"])}
        ctx.ha.ws("backup/config/update", **p)

    def read_back():
        now, _ = _settings(ctx)
        return {k: now.get(k) for k in desired}

    def verify():
        got = read_back()
        return [f"{k} is {got[k]!r}, wanted {v!r}" for k, v in desired.items() if got[k] != v]

    return Plan(title=title, changes=changes, apply=apply, verify=verify, after=read_back,
                kind="backup_config", before=before, name="backup-set", rollback="set the backup settings back")


@command("backup set", "change backup retention, schedule or locations", write=True)
def backup_set(ctx):
    a = ctx.args
    d = {}
    if a.keep is not None:
        d["copies"] = a.keep or None
    if a.keep_days is not None:
        d["days"] = a.keep_days or None
    if a.time:
        d["time"] = a.time if len(a.time) > 5 else a.time + ":00"
    if a.recurrence:
        d["recurrence"] = a.recurrence
    if a.agents:
        d["agents"] = sorted(x.strip() for x in a.agents.split(","))
    if not d:
        raise HAError("nothing to change", "give --keep, --keep-days, --time, --recurrence or --agents", 2)
    return run(ctx, backup_plan(ctx, d))


def _backup_set_args(p):
    p.add_argument("--keep", type=int, help="copies to keep (0 = no limit)")
    p.add_argument("--keep-days", type=int, help="days to keep (0 = no limit)")
    p.add_argument("--time", help="HH:MM local time")
    p.add_argument("--recurrence", choices=["never", "daily", "custom_days"], help="how often automatic backups run")
    p.add_argument("--agents", help="comma list of backup locations (ids from: ha.py backup config)")


backup_set.args = _backup_set_args


@restorer("backup_config")
def restore_backup(ctx, before):
    return backup_plan(ctx, before, title="restore backup settings")
