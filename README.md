# ha-utilities

`ha.py` is a small command-line tool for [Home Assistant](https://www.home-assistant.io/). It handles everyday reads and **safe, reversible changes** from a terminal, with no throwaway scripts against the REST and WebSocket APIs.

```console
$ ha.py state 'media_player.*' --area
media_player.kitchen_speaker  idle     area=Kitchen
media_player.office_speaker   playing  area=Office  media_title="Evening Jazz"

$ ha.py entity set switch.porch_light --area office
PLAN 30d623  entity registry · 1 change
  switch.porch_light  area_id: front_porch → office
ROLLBACK  set the fields back to their before values  (ha.py restore <snapshot printed after apply>)
dry run, nothing changed. re-run with --yes --plan 30d623 to apply
```

## Why

- **Short output.** One line per item, with only the useful fields. Big results go to a file and you get a summary. This matters when the reader is a person skimming, or an AI agent paying for every token.
- **Writes are safe by default.** Every change starts as a dry run that shows exactly what will change and how to undo it. Nothing happens until you re-run with `--yes --plan <id>`. If Home Assistant changed in the meantime, the plan id no longer matches and the write is refused.
- **Everything is reversible.** Before a change, `ha.py` saves a copy of what it's about to touch. It commits that copy to git if your folder is a git repo, applies the change, reads it back to verify, and prints the `ha.py restore` command that undoes it.
- **Easy to extend.** Each command is a small Python function registered with a decorator.

## What it covers

| Area | Read | Change |
|---|---|---|
| States | `state`, `history`, `template`, `logs` | `call` (service calls) |
| Registries | `entities`, `devices`, `areas`, `exposed` | `entity set`, `device set`, `expose` |
| Health | `repairs`, `diagnostics` | |
| Dashboards | `dashboard list`, `dashboard get` | `dashboard save` |
| Automations, scripts | `automation get`, `script get` | `automation save`, `script save` |
| Integrations | `entries`, `homekit list` | `entry enable`, `entry disable`, `entry reload` |
| Backups | `backups`, `backup config` | `backup set` |
| Safety | `snapshots`, `audit` | `restore` |

Full reference: [docs/commands.md](docs/commands.md).

Permanent deletes (backups, integrations, devices) are left out on purpose. Do those in the Home Assistant UI.

## Install

You need Python 3.10 or newer and git. `ha.py` runs on macOS and Linux.

```sh
git clone https://github.com/keithajmani/ha-utilities.git
cd ha-utilities
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`ha.py` re-runs itself under `.venv` automatically, so you can call `./ha.py` directly or symlink it onto your `PATH`:

```sh
ln -s "$PWD/ha.py" ~/.local/bin/ha.py
```

### Connect it to Home Assistant

1. In Home Assistant, create a **long-lived access token**: Profile → Security → Long-lived access tokens → Create token. Registry, dashboard and backup commands need a token from an **administrator** user. A dedicated user just for this tool makes it easy to revoke later.
2. Create the settings folder and save the address and token:

```sh
mkdir -p ~/.config/ha-utilities
echo "http://homeassistant.local:8123" > ~/.config/ha-utilities/url
echo "<your token>" > ~/.config/ha-utilities/token
chmod 600 ~/.config/ha-utilities/token
```

3. Check it works:

```sh
ha.py repairs
ha.py state sun.sun
```

To turn on git checkpoints, run `git init` in `~/.config/ha-utilities`. Every change is then committed before and after. See [docs/configuration.md](docs/configuration.md) for other places the folder can live, environment variables, and `ha.toml` settings.

## How a change works

```mermaid
sequenceDiagram
  participant You
  participant ha as ha.py
  participant Git as Settings folder (git)
  participant HA as Home Assistant
  You->>ha: entity set light.x --area office
  ha->>HA: read current values
  ha-->>You: PLAN 7f3a, changes, rollback
  You->>ha: same command --yes --plan 7f3a
  ha->>HA: re-read; refuse if the plan changed
  ha->>Git: save before-copy, commit "before"
  ha->>HA: apply
  ha->>HA: read back and verify
  ha->>Git: save after-copy, commit "after"
  ha-->>You: APPLIED, UNDO ha.py restore <snapshot>
```

Details, exit codes and what is and isn't undoable: [docs/safety.md](docs/safety.md).

## Using it with an AI agent

`ha.py` was built for a person working with an AI coding agent. The dry-run step is the approval step: the agent runs the command without `--yes`, shows you the plan and rollback, and only applies it with `--yes --plan <id>` after you agree. Because the id is tied to the exact change and the current state, the agent can't apply something different from what you approved. See [docs/ai-agents.md](docs/ai-agents.md) for a ready-made instruction block.

## Extending

Add a function in `ha_lib/commands/`, register it with `@command("name", "help", write=...)`, and it shows up in `ha.py --help`. Writes return a `Plan`, and the safety steps come for free. See [docs/extending.md](docs/extending.md).

## Tests

```sh
.venv/bin/pip install pytest aiohttp
.venv/bin/python -m pytest
```

The tests run `ha.py` end to end against a small fake Home Assistant (`tests/mock_ha.py`). They never touch a real instance.

## Compatibility

Developed and tested against Home Assistant 2026.10. It uses the same REST and WebSocket APIs as the Home Assistant frontend, so older releases may lack some commands (for example `backups` needs the backup integration from 2025.1 or later).

## License

MIT. See [LICENSE](LICENSE).
