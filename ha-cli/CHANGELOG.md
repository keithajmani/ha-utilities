# ha-cli changelog

## 0.1.2 (2026-11-01), tag ha-cli-v0.1.2

- New read command `stats`: Home Assistant's long-term statistics (hourly/daily mean, min, max, sum) for sensors, beyond the normal history window, including removed or renamed sensors. `stats --find TEXT` lists statistic ids.

## 0.1.1 (2026-11-01), tag ha-cli-v0.1.1

- Fix: `history --since` longer than a day returned only the first 24 hours, because Home Assistant ends the window one day after the start unless it is given an end time. `history` now always sends one: `--until`, or now.

## 0.1.0 (2026-10-26), tag ha-cli-v0.1.0

First public release.

- Reads: `state`, `history`, `template`, `logs`, `areas`, `entities`, `devices`, `exposed`, `repairs`, `diagnostics`, `entries`, `homekit list`, `dashboard list/get`, `automation get`, `script get`, `backups`, `backup config`, `snapshots`, `audit`.
- Changes: `entity set`, `device set`, `expose`, `dashboard save`, `automation save`, `script save`, `entry enable/disable/reload`, `backup set`, `call`, `restore`.
- Every change is a dry run until `--yes --plan <id>`. Before-copies, git checkpoints, read-back verification and `restore`.
- Compact output with redaction. Big results go to files.
- `entries` hides ignored discoveries unless `--ignored` is passed.
