"""Connections screen (S2.2): manage and verify connections in-app.

List every configured connection, test reachability live without leaving the
TUI, and store a keyring password — the whole login → test loop in one screen.

Testing a connection is blocking I/O (a network round-trip to the database), so
it runs in a thread worker and the status cell updates via
``call_from_thread`` — the UI never freezes while a test is in flight.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from wiseql.config import PingResult, WiseQLConfig, get_backend, load_active_config, ping

_COLUMNS = ("name", "driver", "target", "user", "secret from", "status")


class LoginModal(ModalScreen[str | None]):
    """Prompt for a password (hidden). Dismisses with the value, or None on Esc."""

    DEFAULT_CSS = """
    LoginModal { align: center middle; }
    LoginModal > Vertical {
        width: 60; height: auto; padding: 1 2;
        background: $surface; border: round $primary;
    }
    LoginModal Static { padding-bottom: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, conn_name: str, user: str) -> None:
        super().__init__()
        self._conn_name = conn_name
        self._user = user

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Password for [b]{self._user}@{self._conn_name}[/b]")
            yield Input(password=True, id="pw", placeholder="password — Enter to save, Esc to cancel")

    def on_mount(self) -> None:
        self.query_one("#pw", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConnectionsScreen(Screen[None]):
    """List connections, test them live, and store keyring passwords."""

    TITLE = "WiseQL — Connections"

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("t", "test", "Test"),
        Binding("l", "login", "Login"),
        Binding("r", "reload", "Reload"),
    ]

    DEFAULT_CSS = """
    ConnectionsScreen #conn-table { height: 1fr; }
    ConnectionsScreen #conn-hint { padding: 0 1; color: $text-muted; }
    """

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self._config_path = config_path
        self._config = WiseQLConfig()
        self._names: list[str] = []  # row order → connection name

    def compose(self) -> ComposeResult:
        yield Header()
        table: DataTable = DataTable(id="conn-table", cursor_type="row", zebra_stripes=True)
        yield table
        yield Static("", id="conn-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#conn-table", DataTable)
        for col in _COLUMNS:
            table.add_column(col, key=col)
        self._reload()
        table.focus()

    # --- data ---------------------------------------------------------------

    def _reload(self) -> None:
        result = load_active_config(self._config_path)
        self._config = result.config
        table = self.query_one("#conn-table", DataTable)
        table.clear()
        self._names = []
        default = self._config.defaults.connection
        for name, conn in sorted(self._config.connections.items()):
            marker = "  (default)" if name == default else ""
            table.add_row(
                f"{name}{marker}",
                conn.driver,
                conn.target,
                conn.user or "—",
                get_backend(conn).describe(name),
                "—",
                key=name,
            )
            self._names.append(name)

        hint = self.query_one("#conn-hint", Static)
        if result.errors:
            hint.update(f"[red]{len(result.errors)} config error(s): {result.errors[0]}[/]")
        elif not self._names:
            hint.update("No connections. Add a [connections.<name>] table to your config.")
        else:
            n = len(self._names)
            hint.update(f"[dim]{n} connection{'s' if n != 1 else ''} · ↑/↓ to select[/]")

    def _selected_name(self) -> str | None:
        table = self.query_one("#conn-table", DataTable)
        if not self._names or table.cursor_row is None or table.cursor_row >= len(self._names):
            return None
        return self._names[table.cursor_row]

    # --- actions ------------------------------------------------------------

    def action_reload(self) -> None:
        self._reload()
        self.notify("Reloaded connections")

    def action_test(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        self.query_one("#conn-table", DataTable).update_cell(
            name, "status", "testing…", update_width=True
        )
        self._test_worker(name)

    @work(thread=True)
    def _test_worker(self, name: str) -> None:
        conn = self._config.connections.get(name)
        if conn is None:
            return
        outcome = ping(name, conn)
        self.app.call_from_thread(self._apply_status, name, outcome)

    def _apply_status(self, name: str, outcome: PingResult) -> None:
        if name not in self._names:
            return  # row went away during a reload
        text = (
            f"[green]✓ {outcome.elapsed_ms} ms[/]"
            if outcome.ok
            else f"[red]✗ {outcome.detail.splitlines()[0][:48]}[/]"
        )
        self.query_one("#conn-table", DataTable).update_cell(
            name, "status", text, update_width=True
        )

    def action_login(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        conn = self._config.connections[name]
        if conn.auth != "keyring":
            self.notify(
                f"'{name}' uses the {conn.auth} backend — nothing to store here",
                severity="warning",
            )
            return

        def _store(password: str | None) -> None:
            if password:
                get_backend(conn).set_password(name, conn, password)
                self.notify(f"Stored password for {name}")

        self.app.push_screen(LoginModal(name, conn.user or "?"), _store)
