# Adding commands

Every module in `ha_lib/commands/` is loaded at start-up. A command is a function registered with `@command`. Its arguments are added by a function stored on `fn.args`.

```
ha.py                 entry point (re-runs under .venv)
ha_lib/
  cli.py              builds the argument parser from the registry, runs a command
  client.py           REST (urllib) and WebSocket (websockets) clients, one login per run
  config.py           settings folder, url, token, ha.toml
  output.py           rows, compact JSON, redaction, local times, big-result files
  safety.py           Plan, plan ids, snapshots, git checkpoints, audit log
  registry.py         @command and @restorer
  commands/           one module per area
```

## A read command

```python
from ..registry import command

@command("zones", "list zones")
def zones(ctx):
    rows = [{"zone": s["entity_id"], "name": s["attributes"].get("friendly_name"),
             "radius": s["attributes"].get("radius")}
            for s in ctx.ha.get("/api/states") if s["entity_id"].startswith("zone.")]
    ctx.out.rows(rows, ["zone", "name", "radius"])

zones.args = lambda p: p.add_argument("--search", help="text in the zone id")
```

`ctx` gives you:

| | |
|---|---|
| `ctx.args` | parsed arguments |
| `ctx.ha.get(path)`, `ctx.ha.post(path, body)`, `ctx.ha.rest(method, path, ...)` | REST |
| `ctx.ha.ws(type, **payload)` | one WebSocket command, returns `result` |
| `ctx.ha.resolve_area(name_or_id)` | area id (`none` → `None`) |
| `ctx.out.rows(rows, cols)` | table output: the first two columns are padded, the rest print as `key=value` |
| `ctx.out.obj(obj, name)` | compact JSON, or saved to `out/` when big |
| `ctx.out.time(value)` | short local time |
| `ctx.s` | settings (`home`, `timezone`, `protected_dashboards`, ...) |

Raise `HAError("what went wrong", "how to fix it")` for a one-line error.

## A change command

A change command builds a `Plan` and hands it to `run()`, which takes care of the dry run, the plan id, snapshots, git, read-back and the audit log.

```python
from ..registry import command, restorer
from ..safety import Change, Plan, run

def zone_radius_plan(ctx, zone, radius, title="zone"):
    cur = ...                                    # read the current radius
    changes = [] if cur == radius else [Change(zone, "radius", cur, radius)]
    return Plan(
        title=title, changes=changes, name="zone-radius",
        apply=lambda: ...,                       # make the change
        verify=lambda: [] if read() == radius else ["radius did not change"],
        after=lambda: {"zone": zone, "radius": read()},
        kind="zone_radius", before={"zone": zone, "radius": cur},
        rollback="set the radius back",
    )

@command("zone set", "change a zone's radius", write=True)
def zone_set(ctx):
    return run(ctx, zone_radius_plan(ctx, ctx.args.zone, ctx.args.radius))

@restorer("zone_radius")
def restore_zone(ctx, before):
    return zone_radius_plan(ctx, before["zone"], before["radius"], title="restore zone")
```

Rules of thumb:

- Put only the fields you change in `before`. The plan id is a hash of the command and `before`, so unrelated fields like timestamps would make every id different.
- Return an empty `changes` list when nothing would change. `run()` then prints "no change needed".
- `kind` + `@restorer(kind)` make a change undoable. Leave `kind` out only when there is truly nothing to restore, as with a service call.
- Never add permanent deletes without a way back.

## Testing

`tests/mock_ha.py` is a small aiohttp server that speaks the REST and WebSocket APIs `ha.py` uses, with in-memory data. Add the endpoints your command needs, then a test in `tests/test_cli.py` that runs `ha.py` through the dry run, `--yes --plan`, and `restore`.

```sh
.venv/bin/pip install pytest aiohttp
.venv/bin/python -m pytest
```
