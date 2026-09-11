# Contributing to Claude Code Telegram Bot

Thanks for helping. This guide covers how to get set up, what a good pull
request looks like here, and what to expect from maintainers. For who the
maintainers are and how to become one, see [MAINTAINERS.md](MAINTAINERS.md).
For what is planned, see [docs/ROADMAP-v2.md](docs/ROADMAP-v2.md).

## What to expect from us

- A reply to every issue and pull request within **seven days**. It may be
  "not now" or "please add X", but it will not be silence.
- New issues and PRs are labelled `needs-triage` until a maintainer has
  looked at them; that label is cleared weekly.
- A first-pass review comment from the Claude Code Review workflow on every
  non-draft PR from a maintainer, followed by a human review before merge.
  The workflow needs repository secrets, so it skips PRs from outside
  contributors; those get the human review only.

## Before you start

1. **Check the roadmap and open PRs.** A lot of common requests already have
   a pull request waiting for review. Comment on that PR or roadmap item
   rather than opening a second one.
2. **Open an issue for anything non-trivial** and say you are working on it.
   For small fixes (typos, a one-function bug) go straight to a PR.
3. **Discuss larger changes first.** Anything that touches the security
   model, adds a setting, changes the database schema, or exceeds about 400
   lines of diff should be agreed in an issue before you write it. This is
   what keeps big PRs from stalling.

## Setting up

Requirements: Python 3.11 or newer, [Poetry](https://python-poetry.org/), Git.

```bash
git clone https://github.com/<your-username>/claude-code-telegram.git
cd claude-code-telegram
make dev          # installs all deps and pre-commit hooks (black, isort on commit)
cp .env.example .env
make test
make lint
```

> **Linux users**: if `make dev` fails with a `DBusErrorResponse` or
> `ItemNotFoundException` for `aiolimiter`, it is a Poetry keyring issue.
> Run `poetry config keyring.enabled false` once, then `make dev` again.

Useful targets:

```bash
make run-debug    # run the bot with debug logging
make run-watch    # auto-restart on file changes
make format       # black + isort
poetry run pytest tests/unit/test_config.py -k test_name -v   # one test
poetry run mypy src                                            # types only
```

## Project layout

```
src/
├── bot/            Telegram layer: orchestrator (agentic mode), classic handlers,
│                   middleware (auth, rate limit, security), shared features
├── claude/         Claude Agent SDK integration, facade, session tracking
├── security/       Auth providers, input validators, rate limiter, audit log
├── storage/        SQLite via aiosqlite, repositories, models, migrations
├── config/         Pydantic settings, feature flags, YAML project loader
├── projects/       Multi-project registry and Telegram topic routing
├── events/         Async event bus and agent handler (webhooks, scheduler)
├── api/            FastAPI webhook server
├── scheduler/      APScheduler jobs persisted in SQLite
├── notifications/  Rate-limited Telegram delivery
└── mcp/            The bot's own MCP server (send image/file to user)
tests/unit/         pytest, asyncio_mode=auto
docs/               Setup, configuration, tools, development, roadmap
```

[CLAUDE.md](CLAUDE.md) has the architecture summary, request flow, and the
five-layer security model. Read it before touching `src/security/` or
`src/claude/`.

## Pull requests

### Scope

- **One concern per PR.** A feature, a fix, or a refactor. Not all three.
  Bundled PRs are the ones that sit unreviewed for months.
- **Keep it under about 400 lines of diff** unless agreed in an issue first.
  Split larger work into a sequence of PRs that each leave `main` working.
- **New settings default to today's behaviour.** Nothing changes for an
  existing install until the operator opts in.
- **Never relax the security model silently.** Anything that widens what a
  Telegram user can make Claude do on the host needs the `security` label
  and lead-maintainer review.

### Requirements

- Tests for behaviour changes. `make test` and `make lint` pass. CI runs
  black, isort, flake8 and the test suite on every PR.
- **If you change dependencies, run `poetry lock` and commit the updated
  `poetry.lock` in the same PR.** CI installs from the committed lock and
  fails the build if the lock and `pyproject.toml` disagree, so a
  `pyproject.toml` dependency change without a matching lock update goes red.
- A line under `[Unreleased]` in `CHANGELOG.md`, in the Keep a Changelog
  style already used there.
- Docs updated where a setting or command changed: `README.md`,
  `.env.example`, `docs/configuration.md`, and `CLAUDE.md` if it affects how
  Claude Code itself should work in this repo.
- The pull request template filled in, including what you tested by hand.
  The suite cannot drive Telegram or the SDK end to end, so a real bot run
  is part of the evidence for anything in the message path.

### AI-assisted contributions

Using Claude Code (or any assistant) to write contributions is welcome; it
is what this project is for. Two rules:

1. You have read and understood every line you are submitting, and you
   answer review comments yourself.
2. The hand-testing section of the PR template describes what *you* ran
   against a real bot. An assistant's claim that it tested something does
   not count.

PRs that fail either rule will be closed with a pointer here.

### Commit messages

Conventional-commit prefixes, imperative mood, and the issue number in the
body or PR:

```
feat: add /sessions command for switching between sessions
fix: parse ResultMessage.subtype so turn-limit stops are reported
docs: correct tools reference after ToolMonitor removal
test: cover scheduler job persistence
refactor: key active requests by conversation
```

### Review and merge

1. The review workflow comments first on maintainer PRs; address anything
   real it finds. It does not run on PRs from outside contributors.
2. A maintainer reviews. Expect questions about tests and security before
   style. Style is handled by the hooks.
3. Merge needs green CI and one approving review; security-sensitive paths
   also need the lead maintainer. See [MAINTAINERS.md](MAINTAINERS.md).
4. Squash-merging is preferred so `main` stays close to one commit per PR;
   a merge commit is fine for a PR whose history is worth keeping.

## Code standards

- Black (88 columns), isort (black profile), flake8, mypy strict. Type hints
  on every function, including tests.
- `structlog` for logging, with key=value context rather than f-strings:
  `logger.info("Session resumed", user_id=user_id, session_id=session_id)`.
- Timezone-aware UTC everywhere: `datetime.now(UTC)`, never
  `datetime.utcnow()`. Model `from_row()` methods guard `fromisoformat()`
  with `isinstance(val, str)` because SQLite returns `datetime` for
  declared TIMESTAMP columns.
- Raise from the project exception hierarchy (`src/exceptions.py`) and chain
  the original: `raise ConfigurationError(...) from e`.
- Tests use `create_test_config()` from `src.config` and mock the Telegram
  and SDK boundaries, not the code under test.

## Issues

Use the issue forms; they ask for the version, mode, and log lines a
maintainer needs. Questions are welcome as issues too, or in GitHub
Discussions where enabled.

## Security

Do not open a public issue for a vulnerability. Use
[GitHub Security Advisories](https://github.com/RichardAtCT/claude-code-telegram/security/advisories/new)
as described in [SECURITY.md](SECURITY.md).

## Community

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind,
assume good intent, and focus feedback on the change rather than the person.
