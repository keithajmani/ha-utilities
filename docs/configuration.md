# Configuration

## The settings folder

`ha.py` keeps its connection details and local state in one folder:

| File | What |
|---|---|
| `url` | Home Assistant address, e.g. `http://homeassistant.local:8123` |
| `token` | long-lived access token (keep it `chmod 600`) |
| `ha.toml` | optional settings (see below) |
| `snapshots/` | before and after copies of every change |
| `logs/ha.log` | audit log |
| `out/` | big results and diffs |
| `diagnostics/` | downloaded diagnostics |

The folder is chosen in this order:

1. `$HA_HOME`, if set.
2. The folder `ha.py` is in, if it contains a `url` file.
3. `~/.config/ha-utilities`.

The default folder is separate from the code, so `git pull` on the code never touches your settings.

**Git checkpoints:** if the settings folder is a git repository, every change is committed before and after. Run `git init` there to turn this on. You can also keep the settings folder inside a repo you already use for your Home Assistant configuration.

## Environment variables

| Variable | Overrides |
|---|---|
| `HA_HOME` | the settings folder |
| `HA_URL` | the `url` file |
| `HA_TOKEN` | the `token` file |

## ha.toml

Copy `ha.toml.example` into the settings folder as `ha.toml`. Every key is optional.

```toml
timezone = ""                    # e.g. "Europe/London"; empty = this computer's zone
big_output_bytes = 4000          # bigger results go to out/ with a summary
max_rows = 50                    # default row cap; --all shows everything
redact_keys = ["password", "token", "access_token", "refresh_token", "api_key", "encryption_key", "secret"]
protected_dashboards = []        # e.g. ["dashboard-generated"]: refused unless --unprotect

[fields]                         # extra attributes `state` shows per domain
media_player = ["media_title"]
climate = ["current_temperature", "temperature", "hvac_action"]
light = ["brightness"]
```

On Python 3.10, reading `ha.toml` needs the `tomli` package, which `requirements.txt` installs. If `ha.toml` exists but can't be read, `ha.py` stops with an error rather than ignoring your settings.

## The virtual environment

`ha.py` re-runs itself with `.venv/bin/python` when a `.venv` folder sits next to it, so the dependencies (`websockets`, `pyyaml`, and `tomli` on 3.10) stay out of your system Python. If a Python upgrade breaks the venv, rebuild it:

```sh
rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Which Home Assistant user

Reading states and calling services work for any user. Registry, dashboard, config entry, backup and system log commands need an **administrator**. A dedicated user for this tool makes its changes easy to spot in the logbook, and easy to revoke: delete the token or the user.
