# Reflex DDNS LiveKit Audio Chat 🎙️

Real-time audio rooms built with [Reflex](https://reflex.dev/) on a **self-hosted, open-source [LiveKit](https://github.com/livekit/livekit) server that runs inside the app's own container**. There is no LiveKit Cloud account, no API key to paste and nothing to configure: install it on [re-ddns](https://github.com/milochen0418/re_ddns) and everyone on your network can talk at `https://livekit.reflex-ddns.com`.

This is the self-hosted sibling of [reflex_livekit_audio_chat](https://github.com/milochen0418/reflex_livekit_audio_chat): same lobby, room and participant UI, but the LiveKit part is embedded instead of rented.

## 📸 Interface Preview

| Lobby | Audio room | Server status |
|:---:|:---:|:---:|
| ![Lobby](docs/images/lobby.png) | ![Room](docs/images/room.png) | ![Settings](docs/images/settings.png) |

## 🌟 Features

- **Lobby**: display name + room name. Invite links (`/?room=<name>`) prefill the room.
- **Audio room**: participant list with speaking indicator, live volume bars and who is muted; mute/unmute; leave; copy invite link.
- **Robust audio**: remote audio elements stay in the DOM, a *Click to enable audio* button appears when the browser blocks autoplay, and you join listen-only if there is no microphone.
- **Embedded LiveKit server**: downloaded (Linux), started, supervised and restarted by the app itself; API keys generated on first start.
- **Calls for other apps**: the `call.join` [DDNS Intent](#-calls-from-other-apps-ddns-intent-calljoin) lets apps like relack open a call in a dialog.
- **`/settings`**: server status for everyone; with `ADMIN_PASSCODE`, the values other apps need (URL, API key/secret), a media IP override, restart, and the server log.
- **No CDN at runtime**: `livekit-client` is vendored in `assets/`, avatars are generated locally.

## 📐 How it works

```
Browser ── https://livekit.reflex-ddns.com ──► re-ddns nginx (TLS, local CA)
  │           /, assets            → Reflex frontend :3000
  │           /_event              → Reflex backend  :8000
  │           /rtc, /twirp/        → Reflex backend  :8000 ─ relay ─► livekit-server 127.0.0.1:7880
  │
  └─ WebRTC audio ── UDP 7882 / TCP 7881, published on the Docker host ──► livekit-server
                     (advertised as rtc.node_ip = EXTERNAL_IP, the host's LAN IP)

smart-app-livekit container
 ├─ reflex run  (frontend :3000, backend :8000)
 │    └─ lifespan task: get livekit-server, write config, start + supervise it
 └─ livekit-server (Apache-2.0)  :7880 localhost only · :7881/tcp · :7882/udp
```

| File | Role |
|------|------|
| `reflex_ddns_livekit_audio_chat/livekit_server.py` | Finds or downloads `livekit-server` (pinned release, checksum-verified), generates keys, writes the config, starts and supervises the process. The server runs detached, so Reflex hot reloads don't drop calls. |
| `reflex_ddns_livekit_audio_chat/livekit_proxy.py` | Same-origin relay on the Reflex backend: WebSocket `/rtc` + `/rtc/v1`, HTTP `/rtc/.../validate` and `/twirp/...` to `127.0.0.1:7880`. |
| `reflex_ddns_livekit_audio_chat/livekit_bridge.py` + `assets/livekit_bridge.js` | Reflex state ↔ LiveKit JS client: token minting, join/leave/mute, room events back into Reflex state. |
| `backend-paths.txt` | Tells re-ddns nginx to send `/rtc` and `/twirp/` to the backend port. |

Signalling therefore goes through the same HTTPS origin as the page. Only the media ports must be published, because nginx cannot proxy WebRTC media.

## 🚀 Install on re-ddns (Agentic App Store)

The App Store catalog (`re_ddns/data/appstore_catalog.json`) has an entry for this app:

```json
{
  "id": "ddns-livekit-audio-chat",
  "subdomain": "livekit",
  "github_repo": "https://github.com/milochen0418/reflex_ddns_livekit_audio_chat.git",
  "app_name": "reflex_ddns_livekit_audio_chat",
  "ports": ["7881:7881", "7882:7882/udp"]
}
```

1. Open `https://aapps.reflex-ddns.com` and install **LiveKit Audio Chat (self-hosted)**. The admin passcode is optional.
2. Open `https://livekit.reflex-ddns.com`, pick a name and a room, and share the invite link.

The first start downloads `livekit-server` (about 17 MB) from GitHub releases. This needs a re-ddns version whose App Store supports the catalog `ports` field and passes `EXTERNAL_IP` to apps.

From the command line:

```bash
./smart_launch.sh -p 7881:7881 -p 7882:7882/udp \
  https://github.com/milochen0418/reflex_ddns_livekit_audio_chat.git reflex_ddns_livekit_audio_chat livekit
```

## 💻 Run locally

Prerequisites: Python 3.11, [Poetry](https://python-poetry.org/docs/#installation) and the LiveKit server binary. On macOS install it with `brew install livekit`; LiveKit publishes no macOS release binaries, while Linux downloads them automatically.

```bash
poetry env use python3.11
poetry install
poetry run ./reflex_rerun.sh
```

Open `http://localhost:3000`. The browser connects to LiveKit via `ws://localhost:8000/rtc` and media goes to the machine's own addresses.

`reflex_rerun.sh` also stops the detached `livekit-server` (port 7880) so the restarted backend starts a fresh one. Runtime files (binary, keys, config, `livekit-server.log`) live in `~/Library/Application Support/reflex_ddns_livekit_audio_chat` on macOS and in `~/.local/share/reflex_ddns_livekit_audio_chat` on Linux.

> If the Docker deployment runs on the same machine, it owns ports 7881/7882. Run the local copy on other media ports:
> `LIVEKIT_RTC_TCP_PORT=7891 LIVEKIT_RTC_UDP_PORT=7892 poetry run ./reflex_rerun.sh`

## ⚙️ Configuration (all optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ADMIN_PASSCODE` | *(empty)* | Unlocks the admin part of `/settings`. |
| `LIVEKIT_NODE_IP` | `EXTERNAL_IP`, else auto | IP address browsers send audio to (`rtc.node_ip`). It can also be set on `/settings`. |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | generated | Fixed credentials, e.g. to share the server with other apps. The secret needs 32+ characters. |
| `LIVEKIT_RTC_TCP_PORT` / `LIVEKIT_RTC_UDP_PORT` | `7881` / `7882` | ICE/TCP port and ICE/UDP mux port. These must match the published ports. |
| `LIVEKIT_PORT` | `7880` | Signalling/API port (localhost only). |
| `LIVEKIT_SERVER_BIN` | PATH, then download | Use a specific `livekit-server` binary. |
| `LIVEKIT_SERVER_VERSION` | `1.13.7` | Release downloaded on Linux. |
| `LIVEKIT_HOME` | see above | Directory for runtime files. |
| `LIVEKIT_PUBLIC_URL` | the app's `api_url` | LiveKit URL handed to browsers. |
| `LIVEKIT_LOG_LEVEL` | `info` | livekit-server log level. |

## 🔗 Use this server from other *.reflex-ddns.com apps

The embedded server is a normal LiveKit server, so any LiveKit SDK can join the same rooms:

- **Client SDKs** (browser, mobile): `wss://livekit.reflex-ddns.com`
- **Server SDKs** (tokens, RoomService): `https://livekit.reflex-ddns.com` from the LAN, or `http://smart-app-livekit:8000` from containers on the re-ddns network
- **API key / secret**: shown on `/settings` (admin). You can also choose them yourself with `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`.

```python
from livekit import api

token = (
    api.AccessToken(API_KEY, API_SECRET)
    .with_identity("relack-user-42").with_name("Amy")
    .with_grants(api.VideoGrants(room_join=True, room="team-standup"))
    .to_jwt()
)
# Browser: new LivekitClient.Room().connect("wss://livekit.reflex-ddns.com", token)
```

## 📞 Calls from other apps (DDNS Intent `call.join`)

Other *.reflex-ddns.com apps open a call in a dialog with [reflex_ddns_auth](https://github.com/milochen0418/reflex_ddns_auth)'s intents. The dialog loads `/intent/call-join`, which joins the LiveKit room right away and answers the caller when the user hangs up:

```python
from reflex_ddns_auth.intent import Intent, intent_host

rx.button("Call", on_click=Intent.start(
    None, "call.join",              # None: whichever installed app provides call.join
    on_result=MyState.call_ended,   # {"status": "ended", "room": <room>} after hang up
    on_cancel=MyState.call_ended,   # {"reason": "closed" | "cancel" | "replaced" | ..., ...} otherwise
    private={"room": call_id},      # posted to the dialog, kept out of the URL
    keep_alive=True,                # other dialogs minimize the call instead of ending it
    single=True,                    # one call at a time: a new call closes the previous one
    label="Call · Design Review",   # shown in the tray while minimized
    title="Design Review", user="amy@example.com", name="Amy",
))
intent_host()  # once per page; delegates microphone + autoplay to the dialog
```

| Param | Meaning |
|-------|---------|
| `room` | Required. Call id, used as the LiveKit room name. Everyone opening the same `room` is in the same call. Use an unguessable id for private calls: the rooms themselves have no access control. Pass it with `private=` so it stays out of URLs and logs. |
| `title` | Shown instead of the id (e.g. the chat room's name). |
| `name` | Display name of the participant. |
| `user` | Stable account id (e.g. an email), the base of the participant identity. |

The params are declared on the intent (`params=`, `required=("room",)`): a call without `room` shows an error, and Close answers `cancel` with `{"error": ...}`. The app also publishes this contract at `/_ddns_intent/manifest`, which the re-ddns intent registry reads, so callers find this app without naming it. Any app that implements `call.join` with these params and events can replace this one.

## 🧪 Tests

Playwright suites live in `testcases/` (see [testcases/README.md](testcases/README.md)):

```bash
poetry run ./run_test_suite.sh smoke_home        # lobby + server running + /rtc relay
poetry run ./run_test_suite.sh two_users_audio   # 2 browsers hear each other, mute/leave sync
ADMIN_PASSCODE=test-pass poetry run ./run_test_suite.sh settings_admin
poetry run ./run_test_suite.sh call_intent       # call.join opened by a fake caller app
```

`two_users_audio` uses Chromium's fake microphone. It checks that inbound audio bytes keep growing and prints the selected ICE pair, so you can see which server port carries the audio.

## 🩺 Troubleshooting

| Symptom | Fix |
|---------|-----|
| Joined but silent, or stuck on *Connecting...* | Media can't reach the server. On `/settings`, *Media IP* must be the Docker host's LAN IP and the media ports must be published (`docker port smart-app-livekit`). Allow UDP 7882 / TCP 7881 in the host firewall. |
| *address already in use* in the status | Another LiveKit instance holds 7881/7882 (e.g. the Docker deployment and a local run on the same Mac). Use other ports, see above. |
| *livekit-server not found on PATH* | macOS: `brew install livekit`. |
| *Click to enable audio* button | The browser blocked autoplay. Click it once. |
| Joined *without microphone* | Mic permission was denied or no device exists. You can still listen. |

## 📄 License

MIT, see [LICENSE](LICENSE). The bundled [livekit-client](https://github.com/livekit/client-sdk-js) (`assets/livekit-client.umd.js`, v2.22.3) and the downloaded [livekit-server](https://github.com/livekit/livekit) are Apache-2.0.
