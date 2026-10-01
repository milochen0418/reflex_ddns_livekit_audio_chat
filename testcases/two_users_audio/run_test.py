"""Two browsers join one room and hear each other through the embedded server.

Chromium's fake microphone (a beep) publishes audio, so we can check real
media flow: the remote audio track's inbound RTP byte counter must grow, and the
selected ICE pairs show which server port carries it.
"""

import os
import secrets
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

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

# Selected ICE pair per peer connection (publisher = our mic uplink, chosen by
# the browser; subscriber = downlink, chosen by the server). Behind Docker
# Desktop the downlink may run over the host's outbound NAT and show up as a
# peer-reflexive candidate (Chrome hides its IP); the uplink goes to the
# published node_ip:port.
_SELECTED_PAIRS = """async () => {
    const room = window.livekitClient && window.livekitClient.room;
    const mgr = room && room.engine && room.engine.pcManager;
    if (!mgr) return [];
    const out = [];
    for (const [label, transport] of [['publisher', mgr.publisher], ['subscriber', mgr.subscriber]]) {
        const pc = transport && transport.pc;
        if (!pc) continue;
        const stats = await pc.getStats();
        const byId = new Map();
        stats.forEach((s) => byId.set(s.id, s));
        let pair = null;
        stats.forEach((s) => {
            if (s.type === 'transport' && s.selectedCandidatePairId) pair = byId.get(s.selectedCandidatePairId);
        });
        if (!pair) continue;
        const local = byId.get(pair.localCandidateId) || {};
        const remote = byId.get(pair.remoteCandidateId) || {};
        out.push({
            label: label,
            local: `${local.candidateType}/${local.protocol} ${local.address || '?'}:${local.port}`,
            remote: `${remote.candidateType}/${remote.protocol} ${remote.address || '?'}:${remote.port}`,
            remote_port: String(remote.port),
            bytes: (pair.bytesSent || 0) + (pair.bytesReceived || 0),
        });
    }
    return out;
}"""


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def join(page: Page, base_url: str, name: str, room: str) -> None:
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.locator('#server-status[data-phase="running"]').wait_for(timeout=120_000)
    page.get_by_placeholder("Enter your name").fill(name)
    page.get_by_placeholder("Enter room to join").fill(room)
    page.get_by_role("button", name="Join Room").click()
    page.wait_for_function(
        "() => document.getElementById('connection-status')?.textContent === 'Connected'"
    )


def wait_for_cards(page: Page, count: int) -> None:
    page.wait_for_function(
        f"() => document.querySelectorAll('.participant-card').length === {count}"
    )


def wait_for_audio(page: Page, label: str, timeout_s: float = 20.0) -> int:
    """Wait until inbound audio bytes are flowing (and still growing)."""
    deadline = time.time() + timeout_s
    previous = -1
    while time.time() < deadline:
        current = page.evaluate(_INBOUND_AUDIO_BYTES)
        if previous > 2000 and current > previous:
            print(f"[{label}] inbound audio bytes: {previous} -> {current}")
            return current
        previous = current
        time.sleep(1.0)
    raise AssertionError(f"[{label}] no inbound audio (last byte count {previous})")


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    output_dir = Path(os.getenv("OUTPUT_DIR", "testcases/two_users_audio/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    headless = env_bool("HEADLESS", True)
    timeout_ms = int(os.getenv("PW_TIMEOUT_MS", "30000"))
    expect_port = os.getenv("EXPECT_MEDIA_PORT", "")
    room = f"e2e-{secrets.token_hex(3)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=int(os.getenv("PW_SLOWMO_MS", "0")),
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        contexts = [
            browser.new_context(
                viewport={"width": 1100, "height": 800},
                ignore_https_errors=True,
                permissions=["microphone"],
            )
            for _ in range(2)
        ]
        alice, bob = (ctx.new_page() for ctx in contexts)
        for page in (alice, bob):
            page.set_default_timeout(timeout_ms)
            page.on("console", lambda msg: msg.type == "error" and print("console:", msg.text))

        try:
            join(alice, base_url, "Alice", room)
            join(bob, base_url, "Bob", room)
            wait_for_cards(alice, 2)
            wait_for_cards(bob, 2)
            print(f"room {room}: both participants visible")

            wait_for_audio(bob, "bob hears alice")
            wait_for_audio(alice, "alice hears bob")

            for label, page in (("alice", alice), ("bob", bob)):
                pairs = page.evaluate(_SELECTED_PAIRS)
                for pair in pairs:
                    print(f"[{label}] {pair['label']}: {pair['local']} -> {pair['remote']} "
                          f"({pair['bytes']} bytes)")
                if expect_port and not any(
                    pair["remote_port"] == expect_port and pair["bytes"] > 0 for pair in pairs
                ):
                    raise AssertionError(f"[{label}] no media over server port {expect_port}")

            alice.screenshot(path=str(output_dir / "alice_in_room.png"), full_page=True)
            bob.screenshot(path=str(output_dir / "bob_in_room.png"), full_page=True)

            # Mute shows up on the other side.
            alice.get_by_title("Mute").click()
            bob.locator(".participant-card", has_text="Alice").locator(
                "svg.lucide-mic-off"
            ).wait_for()
            print("bob sees alice muted")
            alice.get_by_title("Unmute").click()
            bob.locator(".participant-card", has_text="Alice").locator(
                "svg.lucide-mic-off"
            ).wait_for(state="detached")
            print("bob sees alice unmuted")

            # Leaving removes the participant for the other side.
            alice.get_by_title("Leave room").click()
            alice.get_by_role("button", name="Join Room").wait_for()
            wait_for_cards(bob, 1)
            print("bob sees alice leave")

            bob.screenshot(path=str(output_dir / "bob_after_leave.png"), full_page=True)
            return 0
        except Exception:
            for label, page in (("alice", alice), ("bob", bob)):
                try:
                    page.screenshot(path=str(output_dir / f"failure_{label}.png"), full_page=True)
                except Exception:
                    pass
            raise
        finally:
            for ctx in contexts:
                ctx.close()
            browser.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"two_users_audio failed: {exc}", file=sys.stderr)
        raise
