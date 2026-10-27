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
State changes in a time window, oldest first. The state at the start of the window is left out unless you pass `--include-start`.

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

## Automations and scripts

Only automations and scripts created in the UI (stored in `automations.yaml` and `scripts.yaml`) can be read and saved. Ones defined elsewhere in YAML have no config id.

### `automation get <automation entity id|config id> [--yaml | --out file]`
### `script get <script entity id|object id> [--yaml | --out file]`
Prints the config.

### `automation save <id> --from file [--create]` *(change)*
### `script save <id> --from file [--create]` *(change)*
Saves the config from JSON or YAML. Home Assistant reloads automations or scripts after a save. A new id needs `--create`. Undoing a create removes the automation or script again.

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
