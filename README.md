# ha-utilities

A collection of small, independent command-line utilities for [Home Assistant](https://www.home-assistant.io/).

Each utility lives in its own folder, with its own README, requirements and tests. Install only the ones you want.

| Utility | What it does |
|---|---|
| [**ha-cli**](ha-cli/README.md) (`ha.py`) | Reads and safe, reversible changes from the terminal: states, history, registries, dashboards, automations, integrations, backups. Every change is a dry run until you confirm it, can be undone, and is checkpointed in git. Built to work well with AI coding agents. |

## Getting started

```sh
git clone https://github.com/keithajmani/ha-utilities.git
cd ha-utilities/<utility>
```

Then follow that utility's README.

## Shared conventions

- **Safe by default.** Anything that changes Home Assistant shows what it will do first and needs explicit confirmation.
- **No permanent deletes** unless there is a way back.
- **Your settings stay out of the repo.** Addresses, tokens and local state live in each utility's settings folder, never in this repository.
- Python 3.10 or newer, macOS or Linux.

## Releases

Each utility is versioned on its own, with tags named `<utility>-v<version>` (for example `ha-cli-v0.1.0`). Each folder has its own `CHANGELOG.md`.

## Contributing

Issues and pull requests are welcome. New utilities should follow the layout of `ha-cli/`: a folder with its own README, `requirements.txt`, `CHANGELOG.md` and tests that run without a real Home Assistant.

## License

MIT. See [LICENSE](LICENSE).
