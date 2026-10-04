# E2E testcases

This folder contains Playwright end-to-end suites.

## Structure

Each suite lives under:

- `testcases/<suite_name>/run_test.py`
- `testcases/<suite_name>/output/` (artifacts, ignored by git)

The `run_test.py` script should:
- Exit `0` on success
- Exit non-zero on failure
- Write screenshots/logs into `OUTPUT_DIR` (provided by the runner)

## Suites

| Suite | What it checks |
|-------|----------------|
| `smoke_home` | Lobby renders and the embedded LiveKit server reports `running`. |
| `two_users_audio` | Two browsers (fake microphones) join one room, see each other, receive each other's audio over the published ICE port, mute/leave updates. |
| `call_intent` | The `call.join` intent opened by a fake caller page (cross-origin iframe): two callers join under their names, see the title, hear each other; hang up posts `result`; a room passed privately (postMessage after `ready`) joins without appearing in the URL; a call without `room` fails the schema and Close posts `cancel` with the error. |
| `settings_admin` | `/settings` status, admin gate (wrong/right `ADMIN_PASSCODE`), connection info for other apps, server restart, server log. |

## Running

Use the repo-level runner (it manages starting/stopping the Reflex server and collecting artifacts):

```bash
poetry run ./run_test_suite.sh smoke_home
poetry run ./run_test_suite.sh two_users_audio
ADMIN_PASSCODE=test-pass poetry run ./run_test_suite.sh settings_admin
poetry run ./run_test_suite.sh call_intent
```

Locally the embedded server needs a `livekit-server` binary on PATH
(`brew install livekit` on macOS; Linux downloads it automatically).
If the media ports are taken (e.g. by an installed `smart-app-livekit`
container), move them: `LIVEKIT_RTC_TCP_PORT=17881 LIVEKIT_RTC_UDP_PORT=17882`.

To test a deployed instance (e.g. behind re-ddns), run the script directly:

```bash
BASE_URL=https://livekit.reflex-ddns.com EXPECT_MEDIA_PORT=7882 OUTPUT_DIR=/tmp/livekit-e2e \
  poetry run python testcases/two_users_audio/run_test.py
```

Keep `OUTPUT_DIR` outside the repo when the target is a re-ddns **dev-mode** install of
this checkout: that container watches the mounted source, so screenshots written under
`testcases/` hot-reload its backend in the middle of the test.

Optional env vars:
- `BASE_URL` (default `http://127.0.0.1:3000`)
- `HEADLESS=0` to watch the browser
- `PW_SLOWMO_MS=100` to slow actions down so you can see interactions
- `PW_TIMEOUT_MS=60000` to increase Playwright timeouts
- `EXPECT_MEDIA_PORT=7882` to assert that audio flows over this server port (on at least one peer connection)
