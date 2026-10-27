# Changelog

## 0.1.0 (2026-10-26)

First public release.

- Reads: `state`, `history`, `template`, `logs`, `areas`, `entities`, `devices`, `exposed`, `repairs`, `diagnostics`, `entries`, `homekit list`, `dashboard list/get`, `automation get`, `script get`, `backups`, `backup config`, `snapshots`, `audit`.
- Changes: `entity set`, `device set`, `expose`, `dashboard save`, `automation save`, `script save`, `entry enable/disable/reload`, `backup set`, `call`, `restore`.
- Every change is a dry run until `--yes --plan <id>`. Before-copies, git checkpoints, read-back verification and `restore`.
- Compact output with redaction. Big results go to files.
- `entries` hides ignored discoveries unless `--ignored` is passed.
