# AGENTS.md

This file describes how an AI coding agent (and humans) should work in this repository.

## 0) Always read the docs first

Before making changes or running commands, **read all README.md files in this repo** and follow them.

- Repo overview & dev workflow: `README.md`
- E2E test runner conventions: `testcases/README.md`

If you already read them earlier in the session, **re-check** when unsure.

## 1) Python / Poetry requirements (strict)

This project targets **Python 3.11**.

- Prefer Poetry-managed environments.
- If Poetry selected another Python (e.g. 3.12+), switch it:

```bash
poetry env use python3.11
poetry env info
poetry install
```

If `python3.11` is not available on PATH, use an absolute path to the 3.11 executable.

## 2) Default rule: use `poetry run` for scripts

When running any repo scripts, prefer:

- `poetry run <command>`

This ensures the correct virtualenv + dependencies are used.

## 3) Running the app: prefer `reflex_rerun.sh`

When you need to start/restart the Reflex app during development, **prefer the repo helper script**.

Typical usage:

```bash
poetry run ./reflex_rerun.sh
```

Notes:
- Prefer `poetry run ./reflex_rerun.sh` over `poetry run reflex run`.
- This keeps the app startup/restart behavior consistent and helps it run stably on the expected ports: frontend `3000`, backend `8000`.
- If you must run Reflex directly, still do it via Poetry: `poetry run reflex run`.

## 4) Running E2E suites: prefer `run_test_suite.sh`

E2E suites live under `testcases/<suite_name>/run_test.py`.

Do **not** run Playwright suites by starting/stopping the server manually unless you have to.
Instead, use the repo runner, which manages:

- starting/stopping the Reflex server
- setting `OUTPUT_DIR`
- collecting artifacts

Run a suite like this:

```bash
poetry run ./run_test_suite.sh smoke_home
```

Optional environment variables (see `testcases/README.md`):

- `BASE_URL` (default `http://127.0.0.1:3000`)
- `HEADLESS=0` to watch the browser

## 4.5) The embedded LiveKit server

- The app is self-hosted by design: it starts its own `livekit-server` from a Reflex lifespan task (`livekit_server.py`). Do not add LiveKit Cloud settings back.
- Locally (macOS) the binary must be on PATH: `brew install livekit`. Linux downloads the pinned release automatically.
- The server runs detached, so it survives hot reloads. `reflex_rerun.sh` and `run_test_suite.sh` stop it via port `7880`.
- If the Docker deployment (`smart-app-livekit`) runs on the same machine, it owns media ports 7881/7882. Run local copies and suites with `LIVEKIT_RTC_TCP_PORT=7891 LIVEKIT_RTC_UDP_PORT=7892` (and `EXPECT_MEDIA_PORT=7892`).
- Runtime files (binary, keys, config, `livekit-server.log`) live outside the repo: `~/Library/Application Support/reflex_ddns_livekit_audio_chat` (macOS) or `~/.local/share/reflex_ddns_livekit_audio_chat` (Linux).
- Use static icon names: `rx.icon(<Var>)` switches Reflex to lucide's `DynamicIcon`, which makes the Vite dev server load every icon module (about 1,700 requests; pages fail to load behind re-ddns nginx).

## 5) Expectations when acting as an agent

- Prefer the smallest, focused change set.
- After code changes, run the closest relevant check (at minimum the related suite via `run_test_suite.sh`).
- Report outcomes: what you ran, pass/fail, and where artifacts/logs were written.
