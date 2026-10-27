"""Repairs and integration diagnostics."""
from ..registry import command
from .entries import find_entry


@command("repairs", "open repair issues, one line each")
def repairs(ctx):
    issues = ctx.ha.ws("repairs/list_issues")["issues"]
    rows = []
    for i in issues:
        if i.get("ignored") and not ctx.args.ignored:
            continue
        rows.append({"domain": i.get("domain"), "issue": i.get("issue_id"), "severity": i.get("severity"),
                     "key": i.get("translation_key"), "since": ctx.out.time(i.get("created")),
                     "ignored": "yes" if i.get("ignored") else None,
                     "placeholders": i.get("translation_placeholders") or None})
    rows.sort(key=lambda r: (r["domain"] or "", r["issue"] or ""))
    ctx.out.rows(rows, ["domain", "issue", "severity", "key", "since", "ignored", "placeholders"])


repairs.args = lambda p: p.add_argument("--ignored", action="store_true", help="include ignored issues")


@command("diagnostics", "download an integration's diagnostics to a file and print a summary")
def diagnostics(ctx):
    e = find_entry(ctx, ctx.args.entry)
    data = ctx.ha.get(f"/api/diagnostics/config_entry/{e['entry_id']}")
    path = ctx.out.save(f"{e['domain']}-{e['title']}", ctx.out.redact(data), folder="diagnostics")
    d = data.get("data", data) if isinstance(data, dict) else data
    keys = ", ".join(f"{k}[{len(v)}]" if isinstance(v, (list, dict)) else k for k, v in list(d.items())[:15]) if isinstance(d, dict) else type(d).__name__
    ctx.out.line(f"saved {path}")
    ctx.out.line(f"{e['domain']} · {e['title']} · data: {keys}")


diagnostics.args = lambda p: p.add_argument("entry", help="config entry id, or exact title")
