import reflex as rx

from reflex_ddns_livekit_audio_chat import livekit_server
from reflex_ddns_livekit_audio_chat.livekit_bridge import LiveKitBridgeState, bind_livekit
from reflex_ddns_livekit_audio_chat.livekit_proxy import register_livekit_routes
from reflex_ddns_livekit_audio_chat.states.server_state import ServerStatusState
from reflex_ddns_livekit_audio_chat.states.settings_state import SettingsState

# Single source of truth for how LiveKit JS binds to this UI.
LIVEKIT_UI = bind_livekit(LiveKitBridgeState)

_CARD = "w-full max-w-md bg-white p-8 rounded-2xl border border-gray-100 shadow-sm"
_PRIMARY_BUTTON = (
    "w-full bg-violet-600 hover:bg-violet-700 text-white font-semibold py-2.5 "
    "rounded-lg transition-colors flex items-center justify-center mt-4 disabled:opacity-50"
)


def input_field(
    label: str, name: str, placeholder: str, type: str = "text", value: str = ""
) -> rx.Component:
    return rx.el.div(
        rx.el.label(label, class_name="block text-sm font-semibold text-gray-700 mb-1"),
        rx.el.input(
            name=name,
            type=type,
            placeholder=placeholder,
            default_value=value,
            key=value,
            class_name="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition-all",
        ),
        class_name="w-full",
    )


def error_box(message: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.icon("circle-alert", class_name="h-5 w-5 text-red-500 shrink-0"),
        rx.el.p(message, class_name="text-red-700 text-sm break-words min-w-0"),
        class_name="bg-red-50 p-4 rounded-lg flex items-center gap-3 border border-red-100 mb-2",
    )


def server_status_pill() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            class_name=rx.match(
                ServerStatusState.phase,
                ("running", "size-2 rounded-full bg-green-500"),
                ("error", "size-2 rounded-full bg-red-500"),
                "size-2 rounded-full bg-yellow-500 animate-pulse",
            )
        ),
        rx.match(
            ServerStatusState.phase,
            ("running", rx.el.span("Self-hosted LiveKit ", ServerStatusState.version)),
            ("downloading", rx.el.span("Downloading LiveKit server…")),
            ("error", rx.el.span("LiveKit server unavailable")),
            rx.el.span("Starting LiveKit server…"),
        ),
        id="server-status",
        data_phase=ServerStatusState.phase,
        class_name="flex items-center gap-2 bg-white px-3 py-1 rounded-full border border-gray-100 text-xs font-medium text-gray-600",
    )


def info_row(label: str, value: rx.Var | str) -> rx.Component:
    return rx.el.div(
        rx.el.dt(label, class_name="text-gray-500"),
        rx.el.dd(value, class_name="font-mono text-gray-900 break-all text-right"),
        class_name="flex justify-between gap-4 py-1.5 border-b border-gray-50 text-sm",
    )


def readonly_field(label: str, value: rx.Var, field_id: str) -> rx.Component:
    return rx.el.div(
        rx.el.label(label, class_name="block text-xs font-semibold text-gray-500 mb-1"),
        rx.el.input(
            id=field_id,
            value=value,
            read_only=True,
            class_name="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg font-mono text-xs text-gray-800",
        ),
        class_name="w-full",
    )


def server_admin_panel() -> rx.Component:
    return rx.el.div(
        rx.cond(
            SettingsState.server["message"] != "",
            error_box(SettingsState.server["message"]),
            rx.fragment(),
        ),
        rx.el.h2("Connect other apps", class_name="text-sm font-bold text-gray-900"),
        rx.el.p(
            "Any LiveKit SDK can use this server with these values.",
            class_name="text-xs text-gray-500 mb-2",
        ),
        readonly_field("LiveKit URL (client SDKs)", SettingsState.livekit_url, "livekit-url"),
        readonly_field("Server API URL (server SDKs)", SettingsState.server_api_url, "server-api-url"),
        readonly_field("API Key", SettingsState.livekit_api_key, "api-key"),
        readonly_field("API Secret", SettingsState.livekit_api_secret, "api-secret"),
        rx.el.form(
            rx.el.div(
                input_field(
                    "Media IP override (node_ip)",
                    "node_ip",
                    "empty = " + SettingsState.server["node_ip"],
                    value=SettingsState.node_ip_override,
                ),
                rx.el.p(
                    "The IP browsers send audio to (ports TCP ",
                    SettingsState.server["tcp_port"],
                    " / UDP ",
                    SettingsState.server["udp_port"],
                    "). Default: EXTERNAL_IP from re-ddns, i.e. the Docker host's LAN IP.",
                    class_name="text-xs text-gray-500 mt-1",
                ),
                rx.el.button(
                    rx.cond(
                        SettingsState.is_saving,
                        rx.el.span("Saving...", class_name="animate-pulse"),
                        rx.el.div(
                            rx.icon("save", class_name="h-4 w-4"),
                            "Save & Apply",
                            class_name="flex items-center gap-2",
                        ),
                    ),
                    type="submit",
                    disabled=SettingsState.is_saving,
                    class_name=_PRIMARY_BUTTON,
                ),
            ),
            on_submit=SettingsState.save_node_ip,
            reset_on_submit=False,
            class_name="pt-4",
        ),
        rx.el.div(
            rx.el.button(
                rx.icon("rotate-ccw", class_name="h-4 w-4"),
                rx.cond(SettingsState.is_restarting, "Restarting...", "Restart server"),
                on_click=SettingsState.restart_server,
                disabled=SettingsState.is_restarting,
                class_name="flex items-center gap-2 text-sm font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg disabled:opacity-50",
            ),
            rx.el.button(
                rx.icon("refresh-cw", class_name="h-4 w-4"),
                "Refresh",
                on_click=SettingsState.refresh,
                class_name="flex items-center gap-2 text-sm font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg",
            ),
            class_name="flex gap-3 pt-2",
        ),
        rx.el.div(
            rx.el.p(
                "Server log · pid ",
                SettingsState.server["pid"],
                " · started ",
                SettingsState.server["started_at"],
                class_name="text-xs font-semibold text-gray-500 mb-1",
            ),
            rx.el.pre(
                SettingsState.server_log,
                class_name="text-[10px] leading-4 bg-gray-900 text-gray-100 p-3 rounded-lg max-h-64 overflow-auto whitespace-pre-wrap break-all",
            ),
            class_name="pt-4",
        ),
        class_name="space-y-3",
    )


def settings_page() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.a(
                    rx.el.div(
                        rx.icon("arrow-left", class_name="h-4 w-4"),
                        rx.el.span("Back to Lobby"),
                        class_name="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors",
                    ),
                    href="/",
                    class_name="mb-6 inline-block",
                ),
                rx.el.div(
                    rx.icon("settings", class_name="text-violet-500 h-8 w-8"),
                    rx.el.h1(
                        "LiveKit Server",
                        class_name="text-2xl font-bold text-gray-900",
                    ),
                    class_name="flex items-center gap-3 mb-2",
                ),
                rx.el.p(
                    "This app runs its own open-source LiveKit server inside its "
                    "container. No LiveKit Cloud account or keys are needed.",
                    class_name="text-gray-500 text-sm mb-4",
                ),
                rx.el.dl(
                    info_row("Status", ServerStatusState.phase),
                    info_row("Version", ServerStatusState.version),
                    info_row("Media IP", ServerStatusState.node_ip + " (" + ServerStatusState.node_ip_source + ")"),
                    info_row("Media ports", "TCP " + ServerStatusState.tcp_port + " · UDP " + ServerStatusState.udp_port),
                    class_name="mb-6",
                ),
                rx.cond(
                    SettingsState.is_admin_authenticated,
                    server_admin_panel(),
                    rx.el.form(
                        rx.el.div(
                            rx.cond(
                                SettingsState.auth_error != "",
                                error_box(SettingsState.auth_error),
                                rx.fragment(),
                            ),
                            input_field(
                                "Admin Passcode",
                                "admin_passcode",
                                "Enter admin passcode",
                                type="password",
                            ),
                            rx.el.button(
                                rx.cond(
                                    SettingsState.is_authenticating,
                                    rx.el.span(
                                        "Verifying...", class_name="animate-pulse"
                                    ),
                                    rx.el.div(
                                        rx.icon("lock", class_name="h-4 w-4"),
                                        "Unlock Settings",
                                        class_name="flex items-center gap-2",
                                    ),
                                ),
                                type="submit",
                                disabled=SettingsState.is_authenticating,
                                class_name=_PRIMARY_BUTTON,
                            ),
                            class_name="space-y-5",
                        ),
                        on_submit=SettingsState.verify_admin,
                        reset_on_submit=True,
                    ),
                ),
                class_name=_CARD,
            ),
            class_name="flex flex-col items-center justify-center min-h-screen bg-gray-50 px-4 py-10",
        ),
        class_name="font-['Inter']",
    )


def lobby_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.icon("mic-vocal", class_name="h-12 w-12 text-violet-600"),
                rx.el.h1(
                    "Audio Rooms",
                    class_name="text-4xl font-extrabold text-gray-900 tracking-tight",
                ),
                server_status_pill(),
                class_name="flex flex-col items-center gap-4 mb-10",
            ),
            rx.el.div(
                rx.el.form(
                    rx.el.div(
                        rx.cond(
                            LiveKitBridgeState.error_message != "",
                            error_box(LiveKitBridgeState.error_message),
                            rx.cond(
                                ServerStatusState.phase == "error",
                                error_box(ServerStatusState.message),
                                rx.fragment(),
                            ),
                        ),
                        input_field(
                            "Display Name",
                            "username",
                            "Enter your name",
                            value=LiveKitBridgeState.username,
                        ),
                        input_field(
                            "Room Name",
                            "room_name",
                            "Enter room to join",
                            value=LiveKitBridgeState.room_name,
                        ),
                        rx.el.button(
                            rx.cond(
                                LiveKitBridgeState.loading,
                                rx.el.div(
                                    rx.spinner(size="1"),
                                    rx.el.span("Joining..."),
                                    class_name="flex items-center gap-2 justify-center",
                                ),
                                "Join Room",
                            ),
                            type="submit",
                            disabled=LiveKitBridgeState.loading,
                            class_name="w-full bg-violet-600 hover:bg-violet-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-violet-200 mt-2 disabled:opacity-70",
                        ),
                        class_name="space-y-6",
                    ),
                    on_submit=LiveKitBridgeState.join_room,
                    reset_on_submit=False,
                ),
                class_name="w-full max-w-md bg-white p-8 rounded-3xl border border-gray-100 shadow-xl shadow-gray-200/50",
            ),
            rx.el.div(
                rx.el.a(
                    "Server Settings",
                    href="/settings",
                    class_name="text-sm text-gray-500 hover:text-violet-600 transition-colors",
                ),
                class_name="mt-8 text-center",
            ),
            class_name="w-full flex flex-col items-center justify-center min-h-screen bg-gray-50 px-4",
        ),
        class_name="font-['Inter']",
    )


def participant_card(participant: dict) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                participant["initials"],
                class_name="size-12 rounded-full flex items-center justify-center text-white font-bold",
                style={"background_color": participant["avatar_color"]},
            ),
            rx.cond(
                participant["is_speaking"],
                rx.el.div(
                    class_name="absolute -bottom-1 -right-1 size-4 bg-green-500 border-2 border-white rounded-full animate-pulse"
                ),
                rx.fragment(),
            ),
            class_name="relative shrink-0",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    participant["name"],
                    class_name="font-semibold text-gray-900 truncate",
                ),
                rx.el.div(
                    rx.cond(
                        participant["is_muted"],
                        rx.icon("mic-off", class_name="h-3.5 w-3.5 text-red-500"),
                        rx.fragment(),
                    ),
                    rx.el.p(
                        rx.cond(participant["is_local"], "You", "Participant"),
                        class_name="text-xs text-gray-500",
                    ),
                    class_name="flex items-center gap-1 shrink-0",
                ),
                class_name="flex justify-between items-baseline gap-2",
            ),
            rx.el.div(
                LIVEKIT_UI.volume_bar(participant["identity"]),
                class_name="h-1 bg-gray-100 rounded-full mt-2 w-full overflow-hidden",
            ),
            class_name="min-w-0 w-full",
        ),
        class_name="participant-card flex items-center gap-3 p-3 bg-white rounded-xl border border-gray-100 shadow-sm",
    )


def room_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.icon("hash", class_name="h-5 w-5 text-violet-500"),
                        rx.el.h2(
                            LiveKitBridgeState.room_name,
                            class_name="text-xl font-bold text-gray-900",
                        ),
                        rx.el.button(
                            rx.icon("link", class_name="h-4 w-4"),
                            on_click=LiveKitBridgeState.copy_invite_link,
                            title="Copy invite link",
                            class_name="p-1.5 rounded-lg text-gray-400 hover:text-violet-600 hover:bg-violet-50 transition-colors",
                        ),
                        class_name="flex items-center gap-2",
                    ),
                    rx.el.div(
                        rx.el.div(
                            class_name=rx.cond(
                                LiveKitBridgeState.connection_status == "Connected",
                                "size-2 rounded-full bg-green-500",
                                "size-2 rounded-full bg-yellow-500 animate-pulse",
                            )
                        ),
                        rx.el.span(
                            LiveKitBridgeState.connection_status,
                            id="connection-status",
                            class_name="text-sm font-medium text-gray-600",
                        ),
                        class_name="flex items-center gap-2 bg-white px-3 py-1 rounded-full border border-gray-100",
                    ),
                    class_name="flex items-center justify-between mb-8",
                ),
                rx.cond(
                    LiveKitBridgeState.audio_blocked,
                    rx.el.button(
                        rx.icon("volume-2", class_name="h-5 w-5"),
                        "Click to enable audio",
                        on_click=LiveKitBridgeState.enable_audio,
                        class_name="w-full mb-6 flex items-center justify-center gap-2 bg-amber-50 text-amber-800 border border-amber-200 rounded-xl py-3 font-semibold hover:bg-amber-100 transition-colors",
                    ),
                    rx.fragment(),
                ),
                rx.el.div(
                    rx.el.div(
                        rx.el.h3(
                            "Participants",
                            class_name="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4",
                        ),
                        rx.el.div(
                            rx.foreach(LiveKitBridgeState.participants, participant_card),
                            class_name="flex flex-col gap-3",
                        ),
                        class_name="flex-1 overflow-auto pr-2",
                    ),
                    class_name="flex flex-col h-[calc(100vh-280px)]",
                ),
                rx.el.div(
                    rx.el.div(
                        rx.el.button(
                            # Two static icons: a Var icon name makes Reflex use
                            # lucide's DynamicIcon, which loads every icon module.
                            rx.cond(
                                LiveKitBridgeState.is_muted,
                                rx.icon("mic-off", class_name="h-6 w-6"),
                                rx.icon("mic", class_name="h-6 w-6"),
                            ),
                            on_click=LiveKitBridgeState.toggle_mute,
                            title=rx.cond(LiveKitBridgeState.is_muted, "Unmute", "Mute"),
                            class_name=rx.cond(
                                LiveKitBridgeState.is_muted,
                                "p-4 rounded-full bg-red-100 text-red-600 hover:bg-red-200 transition-colors",
                                "p-4 rounded-full bg-violet-100 text-violet-600 hover:bg-violet-200 transition-colors",
                            ),
                        ),
                        rx.el.button(
                            rx.icon("phone-off", class_name="h-6 w-6"),
                            on_click=LiveKitBridgeState.leave_room,
                            title="Leave room",
                            class_name="p-4 rounded-full bg-gray-900 text-white hover:bg-gray-800 transition-colors",
                        ),
                        class_name="flex items-center justify-center gap-6",
                    ),
                    class_name="mt-8 pt-8 border-t border-gray-100",
                ),
                class_name="w-full max-w-2xl bg-white p-8 rounded-3xl border border-gray-100 shadow-xl",
            ),
            class_name="flex flex-col items-center justify-center min-h-screen bg-gray-50 px-4",
        ),
        class_name="font-['Inter']",
    )


def index() -> rx.Component:
    return rx.el.div(
        LIVEKIT_UI.bridge_input(),
        rx.cond(LiveKitBridgeState.is_connected, room_view(), lobby_view()),
    )


app = rx.App(
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400..700&display=swap",
            rel="stylesheet",
        ),
        *LIVEKIT_UI.head_components(),
    ],
)
app.add_page(
    index,
    route="/",
    title="Audio Rooms",
    on_load=[LiveKitBridgeState.on_lobby_load, ServerStatusState.watch],
)
app.add_page(
    settings_page,
    route="/settings",
    title="LiveKit Server",
    on_load=[SettingsState.on_settings_load, ServerStatusState.watch],
)

# The embedded LiveKit server + the /rtc and /twirp relays to it.
app.register_lifespan_task(livekit_server.lifespan)
register_livekit_routes(app)
