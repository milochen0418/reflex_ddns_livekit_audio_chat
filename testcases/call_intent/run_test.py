"""The `call.join` DDNS Intent, opened by another app (a fake caller page).

A fake host on :3999 embeds /intent/call-join the way another
*.reflex-ddns.com app's intent dialog does (cross-origin iframe, microphone
delegated with `allow`). Then:

1. Two callers open the same call: each joins right away under its `name`,
   sees the `title` instead of the call id, and receives the other's audio.
2. Hang up posts a `result` ({"status": "ended", "room": <call id>}) to the caller.
3. A call without `room` shows an error; Close posts `cancel`.
"""

import html
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

from playwright.sync_api import Page, expect, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
TIMEOUT_MS = int(os.environ.get("PW_TIMEOUT_MS", "60000"))
HOST_ORIGIN = "http://localhost:3999"

HOST_PAGE = """<!doctype html><html><body>
<iframe id="frame" src="%s" allow="autoplay; microphone" style="width:720px;height:560px;border:0"></iframe>
<script>
  window.msgs = [];
  window.addEventListener("message", (ev) => {
    if (ev.data && ev.data.type === "ddns-intent") window.msgs.push({origin: ev.origin, ...ev.data});
  });
</script></body></html>"""

_INBOUND_AUDIO_BYTES = """async () => {
    const room = window.livekitClient && window.livekitClient.room;
    if (!room) return -1;
    let total = 0;
    for (const p of room.remoteParticipants.values()) {
        for (const pub of p.audioTrackPublications.values()) {
            const track = pub.track;
            if (!track || !track.receiver) continue;
            const stats = await track.receiver.getStats();
            stats.forEach((r) => { if (r.type === 'inbound-rtp') total += r.bytesReceived || 0; });
        }
    }
    return total;
}"""


class HostHandler(BaseHTTPRequestHandler):
    """Serves the fake caller page; ?src= is the iframe URL."""

    def do_GET(self):
        src = parse_qs(urlparse(self.path).query).get("src", [""])[0]
        body = (HOST_PAGE % html.escape(src, quote=True)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def open_call(page: Page, call_id: str, **params) -> None:
    query = urlencode({**params, "_intent_id": call_id, "_intent_origin": HOST_ORIGIN})
    src = f"{BASE_URL}/intent/call-join?{query}"
    page.goto(f"{HOST_ORIGIN}/?src={quote(src, safe='')}", wait_until="domcontentloaded")


def wait_for_message(page: Page, event: str) -> dict:
    page.wait_for_function(f"window.msgs.some(m => m.event === '{event}')", timeout=TIMEOUT_MS)
    return next(m for m in page.evaluate("window.msgs") if m["event"] == event)


def inbound_audio(page: Page) -> int:
    return page.query_selector("#frame").content_frame().evaluate(_INBOUND_AUDIO_BYTES)


def run():
    output_dir = os.environ.get("OUTPUT_DIR") or os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    shots: dict[str, bytes] = {}

    server = ThreadingHTTPServer(("localhost", 3999), HostHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    room = f"call-{secrets.token_hex(4)}"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                  "--autoplay-policy=no-user-gesture-required"],
        )
        contexts = [browser.new_context(permissions=["microphone"]) for _ in range(2)]
        try:
            print("Two callers open the same call...")
            pages = []
            for ctx, name in zip(contexts, ("Amy", "Ben")):
                page = ctx.new_page()
                page.set_default_timeout(TIMEOUT_MS)
                open_call(page, f"id-{name}", room=room, title="Design Review", name=name,
                          user=f"{name.lower()}@example.com")
                pages.append(page)
            for page in pages:
                frame = page.frame_locator("#frame")
                expect(frame.locator("#connection-status")).to_have_text("Connected", timeout=120_000)
                expect(frame.get_by_role("heading", name="Design Review")).to_be_visible()
                expect(frame.get_by_text(room)).to_have_count(0)
                expect(frame.locator(".participant-card")).to_have_count(2, timeout=TIMEOUT_MS)
                for name in ("Amy", "Ben"):
                    expect(frame.locator(".participant-card", has_text=name)).to_be_visible()
            for page in pages:
                first = inbound_audio(page)
                page.wait_for_timeout(3000)
                second = inbound_audio(page)
                print(f"  inbound audio bytes: {first} -> {second}")
                assert second > first > 0, "no audio received"
            shots["call"] = pages[0].screenshot()

            print("Hang up answers the caller...")
            pages[1].frame_locator("#frame").get_by_role("button", name="Hang up").click()
            result = wait_for_message(pages[1], "result")
            print("  result:", json.dumps(result))
            assert result["id"] == "id-Ben", result
            assert result["data"] == {"status": "ended", "room": room}, result
            expect(pages[0].frame_locator("#frame").locator(".participant-card")).to_have_count(1, timeout=TIMEOUT_MS)

            print("A call without a room shows an error; Close cancels...")
            page = contexts[1].new_page()
            open_call(page, "id-bad", name="Ben")
            frame = page.frame_locator("#frame")
            expect(frame.get_by_text("The call is missing its room or your name.")).to_be_visible(timeout=TIMEOUT_MS)
            shots["missing_room"] = page.screenshot()
            frame.get_by_role("button", name="Close").click()
            cancel = wait_for_message(page, "cancel")
            assert cancel["id"] == "id-bad", cancel

            print("All tests passed!")
        except Exception as e:
            print(f"TEST FAILED: {e}")
            for i, ctx in enumerate(contexts):
                for j, pg in enumerate(ctx.pages):
                    pg.screenshot(path=os.path.join(output_dir, f"failure_{i}_{j}.png"))
            sys.exit(1)
        finally:
            browser.close()
            server.shutdown()
            for name, png in shots.items():
                with open(os.path.join(output_dir, f"{name}.png"), "wb") as f:
                    f.write(png)


if __name__ == "__main__":
    run()
