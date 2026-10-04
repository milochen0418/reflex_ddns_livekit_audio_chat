from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
from typing import Type

import reflex as rx
from livekit import api
from reflex_ddns_auth.intent import IntentPage

from reflex_ddns_livekit_audio_chat import livekit_server

# Bump when assets/livekit_bridge.js changes so browsers drop the cached copy.
_BRIDGE_JS_VERSION = "2"
# Hidden <input> the JS bridge writes room updates into.
BRIDGE_INPUT_ID = "js_msg_input"


def public_ws_url() -> str:
    """LiveKit URL for browsers: this app's own backend, which relays /rtc.

    ``api_url`` is ``http://localhost:8000`` locally and is patched to
    ``https://<subdomain>.reflex-ddns.com`` by the re-ddns smart launcher.
    """
    override = os.environ.get("LIVEKIT_PUBLIC_URL", "").strip()
    if override:
        return override.rstrip("/")
    return re.sub(r"^http", "ws", rx.config.get_config().api_url.rstrip("/"))


class LiveKitBridgeState(rx.State):
    """State that bridges Reflex <-> LiveKit JS client running in the browser."""

    room_name: str = ""
    # What the room is called in the UI: the room name, or the title an intent caller passed.
    room_title: str = ""
    username: str = ""
    connection_status: str = "Disconnected"
    participants: list[dict[str, str | bool]] = []
    is_connected: bool = False
    is_muted: bool = False
    audio_blocked: bool = False
    error_message: str = ""
    loading: bool = False

    @rx.event
    def on_lobby_load(self):
        """Prefill the room from an invite link (/?room=<name>)."""
        room = self.router.url.query_parameters.get("room", "").strip()
        if room and not self.is_connected:
            self.room_name = room

    @rx.event
    async def join_room(self, form_data: dict):
        self.loading = True
        self.error_message = ""
        yield
        try:
            username = form_data.get("username", "").strip()
            room_name = form_data.get("room_name", "").strip()
            if not username or not room_name:
                self.error_message = "Username and Room Name are required."
                return

            connect = await self._connect(room_name, username, identity=username)
            if connect is not None:
                self.room_title = room_name
                yield connect
        except Exception as e:
            logging.exception(f"Error joining room: {e}")
            self.error_message = f"Failed to join room: {str(e)}"
            self.is_connected = False
        finally:
            self.loading = False

    async def _connect(self, room_name: str, username: str, identity: str):
        """Mint a token and return the script that joins the browser to the room.

        Returns None (with ``error_message`` set) when the server is not running.
        """
        server = await asyncio.to_thread(livekit_server.status)
        if server["phase"] != "running":
            detail = f": {server['message']}" if server["message"] else "."
            self.error_message = f"The built-in LiveKit server is {server['phase']}{detail}"
            return None

        api_key, api_secret = livekit_server.api_credentials()
        grant = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
        token = (
            api.AccessToken(api_key, api_secret)
            # Unique identity so the same person can join twice (two tabs, two devices).
            .with_identity(f"{identity}#{secrets.token_hex(2)}")
            .with_name(username)
            .with_grants(grant)
            .to_jwt()
        )

        self.room_name = room_name
        self.username = username
        self.is_connected = True
        self.connection_status = "Connecting..."
        self.is_muted = False
        self.audio_blocked = False
        self.participants = []

        args = ", ".join(json.dumps(a) for a in (public_ws_url(), token, BRIDGE_INPUT_ID))
        return rx.call_script(f"window.livekitClient.connect({args})")

    @rx.event
    async def open_call_intent(self, params: dict):
        """Entry point of the ``call.join`` intent: join ``room`` right away.

        Params: ``room`` (call id, used as the LiveKit room name), ``title``
        (shown instead of the id), ``name`` (display name) and ``user`` (stable
        id of the caller's account, used for the participant identity).
        """
        room_name = params.get("room", "").strip()
        user = params.get("user", "").strip()
        username = params.get("name", "").strip() or user
        self.error_message = ""
        if not room_name or not username:
            self.is_connected = False
            self.error_message = "The call is missing its room or your name."
            return
        self.loading = True
        yield
        try:
            connect = await self._connect(room_name, username, identity=user or username)
            if connect is not None:
                self.room_title = params.get("title", "").strip() or room_name
                yield connect
        except Exception as e:
            logging.exception(f"Error joining call: {e}")
            self.error_message = f"Failed to join the call: {str(e)}"
            self.is_connected = False
        finally:
            self.loading = False

    @rx.event
    def hang_up(self):
        """Leave the call and tell the intent caller that it ended."""
        room_name = self.room_name
        yield from self.leave_room()
        yield IntentPage.finish({"status": "ended", "room": room_name})

    @rx.event
    def leave_room(self):
        yield rx.call_script("window.livekitClient.disconnect()")
        self.is_connected = False
        self.participants = []
        self.connection_status = "Disconnected"
        self.is_muted = False
        self.audio_blocked = False
        self.error_message = ""

    @rx.event
    def toggle_mute(self):
        new_muted_state = not self.is_muted
        self.is_muted = new_muted_state
        yield rx.call_script(
            f"window.livekitClient.setMicrophone({str(not new_muted_state).lower()})"
        )

    @rx.event
    def enable_audio(self):
        yield rx.call_script("window.livekitClient.startAudio()")

    @rx.event
    def copy_invite_link(self):
        room = json.dumps(self.room_name)
        yield rx.call_script(
            "navigator.clipboard.writeText("
            f"window.location.origin + '/?room=' + encodeURIComponent({room}))"
        )
        yield rx.toast.success("Invite link copied.")

    @rx.event
    def handle_js_message(self, json_data: str):
        if not json_data or json_data.strip() == "":
            return

        try:
            data = json.loads(json_data)

            if data.get("type") == "error":
                self.error_message = data.get("message", "Unknown error")
                self.is_connected = False
                self.loading = False
                yield rx.toast.error(f"Error: {self.error_message}")
                return

            if data.get("type") == "warning":
                yield rx.toast.warning(data.get("message", ""))

            if "status" in data:
                self.connection_status = data["status"]
                if data["status"] == "Disconnected":
                    # Our own leave/disconnect is not reported, so this one was unexpected.
                    if self.is_connected:
                        self.error_message = "Disconnected from the room."
                    self.is_connected = False

            if "participants" in data:
                self.participants = data["participants"]

            if "is_muted" in data:
                self.is_muted = data["is_muted"]

            if "audio_blocked" in data:
                self.audio_blocked = data["audio_blocked"]
        except json.JSONDecodeError as e:
            logging.exception(f"Invalid JSON from JS: {e}")
        except Exception as e:
            logging.exception(f"Failed to parse JS message: {e}")



class _LiveKitUI:
    """UI + JS binding helpers for LiveKit."""

    def __init__(self, state_cls: Type[rx.State], *, bridge_input_id: str = BRIDGE_INPUT_ID):
        self._state_cls = state_cls
        self._bridge_input_id = bridge_input_id

    def bridge_input(self) -> rx.Component:
        return rx.el.input(
            id=self._bridge_input_id,
            class_name="hidden",
            on_change=self._state_cls.handle_js_message,
        )

    def volume_bar(self, identity: str, *, width: str = "0%") -> rx.Component:
        return rx.el.div(
            id=f"vol-{identity}",
            class_name="h-full bg-violet-500 transition-all duration-75 rounded-full",
            style={"width": width},
        )

    def head_components(self) -> list[rx.Component]:
        # Served from assets/: no CDN, so rooms work on an offline LAN too.
        return [
            rx.el.script(src="/livekit-client.umd.js"),
            rx.el.script(src=f"/livekit_bridge.js?v={_BRIDGE_JS_VERSION}"),
        ]


def bind_livekit(state_cls: Type[rx.State]) -> _LiveKitUI:
    return _LiveKitUI(state_cls)
