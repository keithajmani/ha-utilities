# Command reference

Every command takes `-h` for help. `ha.py --help` lists them all.

**Output options** (every command): `--json` prints compact JSON, `--all` shows every row (the default cap is 50, set by `max_rows`), and `--limit N` caps the rows.

**Write options** (commands marked *change*): without `--yes` the command is a dry run. `--yes --plan <id>` applies the plan the dry run printed. See [safety.md](safety.md).

Times are printed in your local time zone unless `timezone` is set in `ha.toml`. Durations such as `--since` take `30m`, `6h`, `2d`, or an ISO time like `2026-10-25T21:00`, which is read as local when it has no offset.

---

## States

### `state <entity|glob>...`
Current state, one line per entity. Globs such as `'light.kitchen_*'` match against all states.

| Option | |
|---|---|
| `--area` | show the area (the entity's own, or else its device's) |
| `--name` | show the friendly name |
| `--changed` | show when the state last changed |
| `--attr a,b` | show these attributes (default: the per-domain `fields` in `ha.toml`) |

```console
$ ha.py state 'climate.*' --changed
climate.hallway  heat  changed="Oct 25 21:04"  current_temperature=21.5  temperature=21  hvac_action=idle
```

### `history <entity>... [--since 6h] [--until T] [--include-start]`
State changes in a time window, oldest first. The window runs from `--since` to `--until`, or to now when `--until` is left out, however long it is. The state at the start of the window is left out unless you pass `--include-start`.

### `stats <statistic>... [--since 7d] [--until T] [--period hour|day|...]` / `stats --find TEXT`
Long-term statistics: hourly (or 5-minute, daily, weekly, monthly) mean, min and max for measurement sensors, and sum or state for energy-type sensors. Home Assistant keeps these long after normal history is purged, including for sensors that have since been removed or renamed. `--find` lists statistic ids whose id or name contains the text.

```console
$ ha.py stats --find laundry
$ ha.py stats sensor.laundry_temperature --since 90d --period day
```

### `template '<jinja>'`
Renders a template in Home Assistant and prints the result. Good for quick questions:
`ha.py template '{{ states.light | selectattr("state","eq","on") | list | count }}'`

### `logs [--level ERROR] [--grep text]`
System log entries (what Settings → System → Logs shows), grouped as Home Assistant groups them, newest first, with counts.

### `call <domain.service> [--entity id...] [--data JSON] [--response]` *(change)*
Calls a service (action). A service call is a real-world action, so it is always treated as a change and has **no automatic undo**. `--response` asks for the service's response data and prints it.

```console
$ ha.py call light.turn_on --entity light.desk --data '{"brightness_pct": 40}'
```

---

## Registries and voice assistants

### `areas`
Area ids, names and floors.

### `entities [--domain d] [--area a] [--integration p] [--search text] [--disabled]`
Searches the entity registry. Columns: entity, name, area, `own_area=yes` when the entity has its own area (not inherited from its device), platform, disabled, hidden. Disabled entities are hidden unless `--disabled` is passed.

### `devices [--area a] [--search text]`
Searches the device registry by name, maker or model.

### `exposed [--to alexa|assist|google] [--search text]`
Entities exposed to voice assistants. `alexa` and `google` mean the Home Assistant Cloud integrations; `assist` is the built-in conversation agent.

### `entity set <entity>... [options]` *(change)*
Changes one or more entities in the registry.

| Option | |
|---|---|
| `--name NAME` | new name; `none` to inherit the device's name |
| `--area AREA` | area id or name; `none` to use the device's area |
| `--icon mdi:x` | icon; `none` to clear |
| `--disable` / `--enable` | disable or enable |
| `--hide` / `--unhide` | hide from auto-generated dashboards, or show again |

Entity ids are never renamed by this tool, because a new id breaks automations and dashboards that use the old one.

### `device set <device id|exact name> [--name NAME] [--area AREA]` *(change)*
Renames a device (`none` returns to the integration's name) or moves it to an area.

### `expose <entity>... --to alexa,assist,google --on|--off` *(change)*
Exposes entities to, or hides them from, the given assistants.

---

## Health

### `repairs [--ignored]`
Open repair issues: domain, issue id, severity, translation key, when it was raised. Ignored issues are hidden unless `--ignored` is passed.

### `diagnostics <entry id|exact title>`
Downloads an integration's diagnostics to `diagnostics/<time>_<domain>-<title>.json` (secrets redacted) and prints a one-line summary. The `diagnostics/` folder is git-ignored because diagnostics can hold private details.

---

## Dashboards

### `dashboard list`
Dashboards with url path, mode (storage or yaml), and whether they need admin or are protected in `ha.toml`. `lovelace` is the default Overview.

### `dashboard get <path> [--view v] [--yaml | --out file]`
A dashboard's config, or one view of it (`--view` takes the view's path, title or index). Large configs are saved to `out/` automatically. Use `--out file.json` to choose the file yourself, which is handy as a starting point for `dashboard save`.

### `dashboard save <path> --from file [--view v] [--unprotect]` *(change)*
Saves a dashboard from a JSON or YAML file. With `--view`, the file holds a single view and replaces only that view. The plan shows the view and card counts before and after, plus the first 30 lines of a diff (the full diff is saved to `out/`). Dashboards listed in `protected_dashboards` are refused unless you pass `--unprotect`.

---

## Automations, scripts and scenes

Only automations, scripts and scenes created in the UI (stored in `automations.yaml`, `scripts.yaml` and `scenes.yaml`) can be read and saved. Ones defined elsewhere in YAML have no config id.

### `automation get <automation entity id|config id> [--yaml | --out file]`
### `script get <script entity id|object id> [--yaml | --out file]`
### `scene get <scene entity id|config id> [--yaml | --out file]`
Prints the config.

### `automation save <id> --from file [--create]` *(change)*
### `script save <id> --from file [--create]` *(change)*
### `scene save <id> --from file [--create]` *(change)*
Saves the config from JSON or YAML. Home Assistant reloads automations, scripts or scenes after a save. A new id needs `--create`. Undoing a create removes it again. Saving a scene changes its stored config only. It does not turn the scene on.

### `automation traces <automation>` / `script traces <script>`
Recent runs, newest first, one line each: number, start time, result, trigger (automations only), the step it ended on, and any error. Results are Home Assistant's own words: `finished`, `failed_conditions`, `error`, `aborted`, `cancelled`, `running` and so on. Home Assistant keeps the last 5 runs of each automation or script unless `stored_traces` says otherwise, and keeps them across restarts.

```console
$ ha.py automation traces automation.garage_door_open_alert
1  Nov 08 20:00:00  result=error  trigger="state of cover.garage_door"  step=action/0  error="Action notify.send_message not found"  run=7c1f…
2  Nov 08 17:00:00  result=failed_conditions  trigger="state of cover.garage_door"  step=condition/0  run=2b9a…
```

### `automation trace <automation> [--run N|id] [--yaml | --out file]` / `script trace <script> ...`
One run step by step, in the order it happened: the trigger, each condition as `true` or `false`, and each action with what it did (`called notify.send_message`, `choice 1`, `wait done`, …) and any error. `what` is the step's alias, or else a short description of it. `--run` picks the run: 1 is the newest (the default), 2 the one before, or a run id from `traces`. `--yaml`, `--out` or `--json` give the whole trace, including variables, for when the summary isn't enough.

```console
$ ha.py automation trace automation.garage_door_open_alert
run 7c1f…  Nov 08 20:00:00  error  trigger="state of cover.garage_door"
trigger/0    20:00:00  what="trigger=state cover.garage_door"  result="state of cover.garage_door"
condition/0  20:00:00  what="condition=state input_boolean.guest_mode"  result=true
action/0     20:00:01  what="Tell the kitchen"  result="called notify.send_message"  error="Action notify.send_message not found"
ERROR  Action notify.send_message not found
```

---

## Helpers

Helpers made in **Settings → Helpers** of these types: toggle (`input_boolean`), button (`input_button`), date/time (`input_datetime`), number (`input_number`), dropdown (`input_select`), text (`input_text`), `counter`, `timer` and `schedule`. Helpers set up through an integration's screens (template, group, utility meter, threshold and others) are not covered, and nor are helpers defined in YAML.

### `helper list [--type t] [--search text]`
UI helpers with entity id, type, name and icon.

### `helper get <entity> [--yaml | --out file]`
The helper's config, ready to edit and pass to `helper save`.

### `helper save <entity> --from file` / `helper save <type> --from file --create` *(change)*
Saves a helper's config from JSON or YAML. Home Assistant replaces the whole config on a save, so the file must hold every field you want to keep. The plan lists each field that changes, including fields that the file leaves out, which are removed. To make a new helper, give the type and `--create`. Home Assistant makes the new entity id from the `name`. Undoing a save puts the old config back. Undoing a create removes the helper again.

```console
$ ha.py helper save input_number.bedtime_volume --from vol.yaml
PLAN 33c983  helper · 2 changes
  input_number bedtime_volume  max: 100 → 60
  input_number bedtime_volume  mode: slider → box
ROLLBACK  save the before-copy of the helper back  (ha.py restore <snapshot printed after apply>)
dry run, nothing changed. re-run with --yes --plan 33c983 to apply
```

---

## Integrations

### `entries [--domain d] [--search text] [--problems] [--ignored]`
Config entries with their state (`loaded`, `not_loaded`, `setup_retry`, `setup_error`…), who disabled them, and the failure reason. `--problems` keeps only enabled entries that aren't loaded. Discoveries you clicked **Ignore** on are not real integrations, so they are hidden unless `--ignored` is passed.

### `entry disable <entry>` / `entry enable <entry>` *(change)*
Disables or enables an integration entry. Disabling unloads it and its entities become unavailable. Undo with `ha.py restore`.

### `entry reload <entry>` *(change)*
Reloads an entry and checks it comes back `loaded`. There is nothing to undo.

### `homekit list`
HomeKit Bridge entries: mode, included domains, counts of included and excluded entities, and accessory count (read from each bridge's diagnostics).

---

## Backups

### `backups`
Backups, newest first: date, name, size, which locations hold a copy, and whether it was automatic. A footer shows the last and next automatic backup.

### `backup config`
Automatic backup settings: copies and days kept, schedule, locations, and what's included. The encryption key always prints as `«redacted»`.

### `backup set [--keep N] [--keep-days N] [--time HH:MM] [--recurrence never|daily|custom_days] [--agents a,b]` *(change)*
Changes retention, schedule or locations. `0` for `--keep` or `--keep-days` means no limit. Location ids come from `ha.py backup config`.

Deleting backups is deliberately not supported. Do it in Settings → System → Backups.

---

## Safety

### `restore <snapshot>` *(change)*
Puts a before-copy back. It goes through the same dry run and `--yes --plan` steps as any change, and is itself undoable.

### `snapshots`
Before-copies, newest first, with the command that made each one.

### `audit [--since 1d] [--reads]`
What `ha.py` did: planned, applied, refused, failed, with plan ids and snapshots. Reads are included only with `--reads`.
