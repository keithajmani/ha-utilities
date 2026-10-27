# Using ha.py with an AI agent

AI coding agents are good at Home Assistant chores: moving entities between areas, rewriting a dashboard card, finding what's flooding the log. Left alone, they write a new throwaway API script each time, dump huge JSON blobs, and make changes you never saw. `ha.py` gives them one tool with short output and a built-in approval step.

## Why it works well

- **Fewer tokens.** One line per item, and big results go to files with a summary.
- **Approval is part of the tool.** A change without `--yes --plan <id>` is only a plan. The agent shows you the plan, and the id ties the approval to that exact change and the current state.
- **Mistakes are cheap.** Every change has a before-copy, git commits, and `ha.py restore`.
- **An audit trail.** `ha.py audit` shows everything the agent ran.

## Instructions to give your agent

Paste this into your agent's instructions, such as `CLAUDE.md`, `AGENTS.md`, or a skill, and adjust the path:

```markdown
## Home Assistant

Use `~/ha-utilities/ha-cli/ha.py` for every Home Assistant read and change. Do not write
your own REST or WebSocket scripts. `ha.py --help` and `ha.py <command> --help`
list the commands.

- Reads (state, history, entities, devices, repairs, logs, dashboard get, ...) are
  safe to run. Prefer them to guessing.
- Changes: first run the command WITHOUT --yes. Show me the PLAN lines and the
  ROLLBACK line, and wait for my explicit yes for that change. Then run the same
  command with `--yes --plan <id>`. Never pass --yes without my yes. If it is
  refused with "plan id mismatch", show me the new plan and ask again.
- After a change, tell me the UNDO line it printed.
- Never use --unprotect unless I say so. `call` (service calls) cannot be undone,
  so say that when you ask.
- If a task needs something ha.py can't do, propose a new command (what it does,
  and how it's undone) instead of writing a one-off script.
```

## Running on another machine

If the agent runs somewhere that can't reach your Home Assistant (a cloud sandbox, say), have it run `ha.py` through whatever remote shell it has on a machine inside your network. Only that machine needs the token.
