# Safety model

`ha.py` has three kinds of command.

| Kind | Examples | What happens |
|---|---|---|
| **Read** | `state`, `entities`, `dashboard get` | Runs immediately. Secrets are redacted. |
| **Change** | `entity set`, `dashboard save`, `call` | Dry run unless `--yes --plan <id>`. Before-copy, git checkpoint, read-back. |
| **Permanent** | deleting backups, integrations, devices | Not in the tool. Use the Home Assistant UI. |

## The steps of a change

1. **Plan.** The command reads the current values and works out the exact changes. If nothing would change, it says `no change needed` and stops.
2. **Show.** It prints `PLAN <id>`, one line per change (`target  field: before → after`), any extra detail such as a diff, and a `ROLLBACK` line.
3. **Stop**, unless `--yes` was given. A dry run changes nothing.
4. **Check the id.** With `--yes`, the plan is worked out again and its id must equal `--plan`. The id is a hash of the command and the current values of the fields being changed. If someone edited the same thing in the UI since the dry run, or the command is different, the ids differ and the change is refused (exit code 3).
5. **Before-copy.** The current values go to `snapshots/<time>_<name>.json`. If the settings folder is a git repo, the file is committed: `ha.py: <name> (before)`.
6. **Apply** the change.
7. **Read back** and compare with what was asked. Any difference prints `VERIFY FAILED` and exits 1.
8. **After-copy.** The read-back values are added to the snapshot, and the snapshot and audit log are committed: `ha.py: <name> (after)`.
9. **Report.** It prints `APPLIED`, the commit ids, and `UNDO  ha.py restore <snapshot>`.

Git commits include only `ha.py`'s own files, so other work in the same repo is never swept in.

## Undo

`ha.py restore <snapshot>` turns the before-copy back into a plan and runs it through the same steps, including the dry run. If the thing was changed again after the snapshot, the restore plan shows that, so you can decide.

| Change | Undo |
|---|---|
| `entity set`, `device set`, `expose` | restores the changed fields |
| `dashboard save` | restores the whole dashboard config |
| `automation save`, `script save` | restores the old config, or removes it if it was created |
| `entry disable` / `enable` | flips it back |
| `backup set` | restores the changed settings |
| `entry reload` | nothing to undo |
| `call` | **no automatic undo.** Call the opposite service if there is one |

## Redaction

Any key whose name contains one of the `redact_keys` words (password, token, api_key, encryption_key, secret…) prints as `«redacted»`. This applies to output, diagnostics files, and big results saved to `out/`. The access token itself is never printed or logged.

## Audit log

Every command adds one JSON line to `logs/ha.log`: time, command, result (`read`, `planned`, `no-op`, `refused`, `applied`, `verify-failed`, `error`), plan id and snapshot. `ha.py audit` reads it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success, including a dry run or "no change needed" |
| 1 | error (bad token, can't reach HA, not found, verify failed) |
| 2 | usage error (missing arguments, nothing to change) |
| 3 | refused: plan id mismatch, or a protected dashboard |
| 130 | interrupted |

## What it does not protect against

- A service call can't be undone automatically.
- The undo restores Home Assistant's configuration, not side effects. A disabled integration's entities will have gaps in history, for example.
- The token is as powerful as the user it belongs to. Keep it readable only by you (`chmod 600`), and revoke it in your Home Assistant profile if it leaks.
