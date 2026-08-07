# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single, outbound-only Python Discord bot (`sylvanova_apworld_bot`). It
binds no local port and uses no database — it connects out to the Discord gateway and
the GitHub API. See `README.md` for the product overview and the standard Docker/venv/test
commands; the notes below only cover non-obvious cloud specifics.

### Environment layout

- Python 3.12. Dependencies are installed into a project virtualenv at `.venv` (created
  during environment setup; the `python3.12-venv` system package is baked into the VM
  snapshot). The startup update script refreshes deps with `.venv/bin/pip install -e .`.
- Run everything through the venv interpreter, e.g. `.venv/bin/python ...`. The
  `sylvanova-apworld-bot` console script is also on `.venv/bin`.
- Source lives under `src/` (a `src` layout). When running modules directly, prefer
  `PYTHONPATH=src` (the editable install already wires this up, but tests/docs use it
  explicitly).

### Test / lint

- Tests: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`. They mock
  archive bytes and need no network or credentials.
- No linter/formatter is configured in this repo. Use `.venv/bin/python -m compileall src tests`
  as a basic syntax gate.

### Running the bot

- Requires `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, and `GITHUB_TOKEN` (see `.env.example`).
  Without them the process fails fast with a clear `RuntimeError`.
- Non-obvious gotcha: `IndexPullRequestClient` calls the GitHub `get_repo` API inside
  `ApworldBot.__init__`, so an invalid/missing `GITHUB_TOKEN` raises a `401 Bad credentials`
  error at startup — *before* the Discord login is ever attempted. Provide a valid GitHub
  token when debugging Discord connectivity.

### Testing core functionality without credentials

- The bot's core action — turning a GitHub release `.apworld` URL into discovered metadata
  and index TOML — needs only outbound `github.com` access (no Discord/GitHub tokens):
  `discover_from_release_url(url)` + `render_discovered_toml(world)`. This is the fastest
  way to smoke-test the discovery pipeline against a real release asset.
