"""The WiseQL Textual application.

A thin shell: it opens to the project picker, then hands off to a per-project
dashboard. All real UI lives in the picker (``tui/picker.py``) and the dashboard
(``tui/dashboard.py``); the app just wires project navigation and owns Help.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from wiseql import __version__
from wiseql.ai import get_provider
from wiseql.tui.theme import THEME

HELP_TEXT = f"""\
[b]WiseQL v{__version__} — Help[/b]

[b]Project picker[/b] (startup)
  ↑/↓ · enter   Open a project
  n             New project
  esc           Quit

[b]Project dashboard[/b]
  1 / 2 / 3     Overview · Recipes · Runs tabs
  ↑/↓ · enter   Select a recipe (preview) or open a run
  F2            Run the selected recipe (live DAG view)
  F3            Connections (list · test · login)
  Ctrl+T        Sync DB schema → context/tables.md
  Ctrl+N        New project
  esc           Back to the project picker

[dim]macOS: F-keys are media keys by default — press Fn+F-key, or enable
"Use F1, F2, etc. keys as standard function keys" in Keyboard settings.[/dim]

[b]What is WiseQL?[/b]
A terminal app that runs SQL [i]recipes[/i] — complex database reads broken
into a DAG of small steps — with live run views, per-step reports, and
assertions that catch data issues automatically.

[dim]Docs: https://wiseql.dev   ·   Esc to close[/dim]
"""


class HelpScreen(ModalScreen[None]):
    """Help overlay, closes on any key."""

    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > Static {
        width: 78; max-width: 90%; padding: 1 2;
        background: $surface; border: round $primary;
    }
    """

    def compose(self):
        yield Static(HELP_TEXT)

    def on_key(self, event) -> None:
        # Esc (like every other window) — or any key — closes Help. Stop the
        # event so it can't leak to the screen underneath (else Esc would also
        # trigger that screen's own Esc action).
        event.stop()
        self.dismiss()


class WiseQLApp(App[None]):
    """Shell app: opens the project picker, navigates to project dashboards."""

    TITLE = "WiseQL"
    SUB_TITLE = "the wise data browser"
    CSS = THEME

    BINDINGS = [Binding("ctrl+q", "quit", "Quit", show=False)]

    def __init__(self, config_path: Path | None = None, projects_dir: Path | None = None) -> None:
        super().__init__()
        self.ai = get_provider()  # NullProvider until the [ai] add-on (Sprint 6)
        self.config_path = config_path  # None → $WISEQL_CONFIG / standard location
        self._projects_dir_override = projects_dir
        self.active_project: Path | None = None

    @property
    def projects_dir(self) -> Path:
        """The configured projects folder — independent of the working directory."""
        if self._projects_dir_override is not None:
            return Path(self._projects_dir_override)
        from wiseql.config import load_active_config

        return load_active_config(self.config_path).config.projects_root

    def on_mount(self) -> None:
        self.show_picker()

    # --- project navigation -------------------------------------------------

    def open_project(self, path: Path) -> None:
        """Make ``path`` the active project and show its dashboard."""
        from wiseql.tui.dashboard import ProjectDashboardScreen

        self.active_project = Path(path)
        self.sub_title = f"project · {self.active_project.name}"
        # Replace a current dashboard (switching projects) rather than stacking.
        if isinstance(self.screen, ProjectDashboardScreen):
            self.pop_screen()
        self.push_screen(ProjectDashboardScreen(Path(path), self.config_path))

    def show_picker(self) -> None:
        """Show the project picker (the app's entry screen)."""
        from wiseql.tui.picker import ProjectPickerScreen

        if any(isinstance(s, ProjectPickerScreen) for s in self.screen_stack[:-1]):
            self.pop_screen()  # a picker is underneath — pop back to it
        elif not isinstance(self.screen, ProjectPickerScreen):
            self.push_screen(ProjectPickerScreen(self.projects_dir))

    def action_new_project(self) -> None:
        from wiseql.tui.wizard import ProjectWizard

        def _create(values: dict | None) -> None:
            if values is None:
                return
            from wiseql.project import scaffold_project

            dest = self.projects_dir / values["name"]
            try:
                self.projects_dir.mkdir(parents=True, exist_ok=True)
                scaffold_project(dest, values["name"], description=values["description"])
            except (FileExistsError, OSError) as exc:
                self.notify(str(exc), severity="error")
                return
            self.notify(f"Created project '{values['name']}'")
            self.open_project(dest)

        self.push_screen(ProjectWizard(), _create)
