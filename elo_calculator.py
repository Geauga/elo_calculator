"""Tkinter desktop interface for the twelve-player Elo calculator."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from elo_model import (
    DEFAULT_PLAYER_COUNT,
    INITIAL_RATING,
    MAX_CUSTOM_SCORE,
    MAX_ELO_DECIMAL_PLACES,
    MAX_GAMES_TO_WIN,
    MAX_K_FACTOR,
    MAX_PLAYER_COUNT,
    MIN_K_FACTOR,
    MIN_PLAYER_COUNT,
    SCORE_MODE_CUSTOM,
    SCORE_MODE_FIXED,
    WinCondition,
    validate_elo_decimal_places,
    validate_k_factor,
)
from elo_simulator import (
    simulate_first_to_n_league,
    simulate_first_to_n_season,
    simulation_limit,
)
from elo_storage import AuditLog, BackupManager, LeagueCollection


THEME_PALETTES = {
    "light": {
        "background": "#f3f3f3",
        "panel": "#ffffff",
        "field": "#ffffff",
        "foreground": "#1f1f1f",
        "muted": "#5d5d5d",
        "button": "#fbfbfb",
        "button_active": "#e5e5e5",
        "border": "#d1d1d1",
        "selection": "#0067c0",
        "selection_text": "#ffffff",
        "disabled": "#9b9b9b",
    },
    "dark": {
        "background": "#202020",
        "panel": "#2b2b2b",
        "field": "#323232",
        "foreground": "#f5f5f5",
        "muted": "#c7c7c7",
        "button": "#323232",
        "button_active": "#454545",
        "border": "#515151",
        "selection": "#0078d4",
        "selection_text": "#ffffff",
        "disabled": "#858585",
    },
}


def application_data_directory() -> Path:
    """Return a persistent, user-writable directory for app data."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "EloLeagueCalculator"


def load_theme(path: Path) -> str:
    if not path.exists():
        return "light"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "light"
    theme = data.get("theme") if isinstance(data, dict) else None
    return theme if theme in THEME_PALETTES else "light"


def save_theme(path: Path, theme: str) -> None:
    if theme not in THEME_PALETTES:
        raise ValueError("Theme must be light or dark.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps({"theme": theme}, indent=2), encoding="utf-8")
    temporary_path.replace(path)


APP_DATA_DIRECTORY = application_data_directory()
DATA_FILE = APP_DATA_DIRECTORY / "elo_league_data.json"
SETTINGS_FILE = APP_DATA_DIRECTORY / "app_settings.json"
BACKUP_DIRECTORY = APP_DATA_DIRECTORY / "backups"
AUDIT_LOG_FILE = APP_DATA_DIRECTORY / "audit_log.jsonl"
LOCK_FILE = APP_DATA_DIRECTORY / "app.lock"


class ApplicationInstanceLock:
    """Hold an OS-level file lock for the lifetime of an app instance."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_file.close()
            return False
        self._file = lock_file
        return True

    def release(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


class EloCalculatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.load_warning: str | None = None
        self.opened_new_league_after_load_failure = False
        self.backups = BackupManager(BACKUP_DIRECTORY)
        self.audit_log = AuditLog(AUDIT_LOG_FILE)
        try:
            self.collection = LeagueCollection.load(DATA_FILE)
        except ValueError as error:
            self.collection = LeagueCollection.new()
            self.load_warning = str(error)
            self.opened_new_league_after_load_failure = True
        self.league = self.collection.active.league

        if self.collection.migrated_from_single_league:
            try:
                self.backups.create(self.collection, "migrated-single-league")
                self.collection.save(DATA_FILE)
            except OSError as error:
                self.load_warning = (
                    f"The existing league was loaded but not upgraded: {error}"
                )
            else:
                try:
                    self.audit_log.append(
                        "migration",
                        self.collection.active.id,
                        self.collection.active.name,
                        "Upgraded the original single-league save to "
                        "multi-league storage.",
                    )
                except OSError as error:
                    self.load_warning = (
                        "The league database was upgraded, but the migration "
                        f"could not be added to the activity log: {error}"
                    )

        self.league_name_to_id: dict[str, str] = {}
        self.league_var = tk.StringVar(value=self.collection.active.name)
        self.heading_var = tk.StringVar()
        self.player_name_to_id: dict[str, int] = {}
        self.winner_var = tk.StringVar()
        self.loser_var = tk.StringVar()
        self.loser_games_var = tk.StringVar(value="0")
        self.winner_games_var = tk.StringVar(value="3")
        self.winner_score_var = tk.StringVar(value="3 -")
        self.theme_var = tk.StringVar(value=load_theme(SETTINGS_FILE))
        self.preview_var = tk.StringVar(
            value="Select two different players to preview the Elo change."
        )
        self.status_var = tk.StringVar(value=f"Data file: {DATA_FILE.name}")

        self._configure_window()
        self._build_ui()
        self._refresh_all()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.load_warning:
            warning_title = (
                "Saved data not loaded"
                if self.opened_new_league_after_load_failure
                else "Startup warning"
            )
            warning_text = self.load_warning
            if self.opened_new_league_after_load_failure:
                warning_text += (
                    "\n\nA new league has been opened. The existing file has "
                    "not been overwritten."
                )
            self.root.after(
                100,
                lambda: self._show_warning(
                    warning_title,
                    warning_text,
                    parent=self.root,
                ),
            )

    def _configure_window(self) -> None:
        self.root.title("12-Player Elo League")
        self.root.geometry("1100x760")
        self.root.minsize(940, 650)
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self._apply_theme(self.theme_var.get(), save=False)

    def _set_title_bar_theme(self, window: tk.Misc) -> None:
        """Match a Windows title bar to the selected application theme."""
        if os.name != "nt":
            return
        try:
            import ctypes

            window.update_idletasks()
            get_parent = ctypes.windll.user32.GetParent
            get_parent.argtypes = (ctypes.c_void_p,)
            get_parent.restype = ctypes.c_void_p
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            set_window_attribute.argtypes = (
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.c_uint,
            )
            set_window_attribute.restype = ctypes.c_long
            window_handle = get_parent(window.winfo_id())
            use_dark = ctypes.c_int(self.theme_var.get() == "dark")
            for attribute in (20, 19):
                result = set_window_attribute(
                    window_handle,
                    attribute,
                    ctypes.byref(use_dark),
                    ctypes.sizeof(use_dark),
                )
                if result == 0:
                    break
        except (AttributeError, OSError, tk.TclError):
            # Older Windows versions may not expose the dark-title-bar flag.
            pass

    def _center_dialog(self, dialog: tk.Toplevel, parent: tk.Misc) -> None:
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        x = min(max(0, x), max(0, dialog.winfo_screenwidth() - width))
        y = min(max(0, y), max(0, dialog.winfo_screenheight() - height))
        dialog.geometry(f"+{x}+{y}")

    def _configure_dialog(
        self,
        dialog: tk.Toplevel,
        parent: tk.Misc | None = None,
        *,
        resizable: tuple[bool, bool] = (False, False),
    ) -> tk.Misc:
        """Apply one visual and modal standard to every in-app dialog."""
        owner = parent or self.root
        colors = THEME_PALETTES[self.theme_var.get()]
        dialog.configure(background=colors["background"])
        dialog.transient(owner)
        dialog.resizable(*resizable)
        dialog.grab_set()
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.after_idle(lambda: self._set_title_bar_theme(dialog))
        return owner

    def _ask_value(
        self,
        title: str,
        prompt: str,
        initial_value: str | int,
        *,
        integer: bool = False,
        minimum: int | None = None,
        maximum: int | None = None,
        parent: tk.Misc | None = None,
    ) -> str | int | None:
        """Show a themed text or whole-number prompt."""
        owner = parent or self.root
        previous_grab = owner.grab_current()
        dialog = tk.Toplevel(owner, name="themed_input_dialog")
        dialog.title(title)
        self._configure_dialog(dialog, owner)

        content = ttk.Frame(dialog, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        ttk.Label(
            content,
            text=prompt,
            wraplength=430,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        value_var = tk.StringVar(value=str(initial_value))
        if integer:
            input_widget = ttk.Spinbox(
                content,
                textvariable=value_var,
                from_=minimum if minimum is not None else -999999,
                to=maximum if maximum is not None else 999999,
                width=18,
            )
        else:
            input_widget = ttk.Entry(content, textvariable=value_var, width=36)
        input_widget.grid(row=1, column=0, sticky="ew")

        error_var = tk.StringVar()
        ttk.Label(
            content,
            textvariable=error_var,
            style="Error.TLabel",
            wraplength=430,
        ).grid(row=2, column=0, sticky="ew", pady=(6, 0))

        result: dict[str, str | int | None] = {"value": None}

        def accept() -> None:
            raw_value = value_var.get()
            if integer:
                try:
                    converted = int(raw_value)
                except ValueError:
                    error_var.set("Enter a whole number.")
                    input_widget.focus_set()
                    return
                if minimum is not None and converted < minimum:
                    error_var.set(f"Enter a number from {minimum} to {maximum}.")
                    input_widget.focus_set()
                    return
                if maximum is not None and converted > maximum:
                    error_var.set(f"Enter a number from {minimum} to {maximum}.")
                    input_widget.focus_set()
                    return
                result["value"] = converted
            else:
                result["value"] = raw_value
            dialog.destroy()

        buttons = ttk.Frame(content)
        buttons.grid(row=3, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="OK", command=accept).pack(side="left")

        dialog.bind("<Return>", lambda _event: accept())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        dialog.minsize(max(380, dialog.winfo_reqwidth()), dialog.winfo_reqheight())
        self._center_dialog(dialog, owner)
        input_widget.focus_set()
        input_widget.selection_range(0, "end")
        owner.wait_window(dialog)
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        return result["value"]

    def _ask_text(
        self,
        title: str,
        prompt: str,
        initial_value: str,
        parent: tk.Misc | None = None,
    ) -> str | None:
        result = self._ask_value(
            title, prompt, initial_value, parent=parent
        )
        return result if isinstance(result, str) else None

    def _ask_integer(
        self,
        title: str,
        prompt: str,
        initial_value: int,
        minimum: int,
        maximum: int,
        parent: tk.Misc | None = None,
    ) -> int | None:
        result = self._ask_value(
            title,
            prompt,
            initial_value,
            integer=True,
            minimum=minimum,
            maximum=maximum,
            parent=parent,
        )
        return result if isinstance(result, int) else None

    def _message_dialog(
        self,
        title: str,
        message: str,
        *,
        kind: str = "information",
        confirmation: bool = False,
        parent: tk.Misc | None = None,
    ) -> bool:
        """Show a consistently themed notice or confirmation dialog."""
        owner = parent or self.root
        previous_grab = owner.grab_current()
        dialog = tk.Toplevel(owner, name="themed_message_dialog")
        dialog.title(title)
        self._configure_dialog(dialog, owner)

        content = ttk.Frame(dialog, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        ttk.Label(
            content,
            text=kind.title(),
            style=f"{kind.title()}.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(
            content,
            text=message,
            wraplength=500,
            justify="left",
        ).grid(row=1, column=0, sticky="ew")

        result = {"accepted": False}

        def accept() -> None:
            result["accepted"] = True
            dialog.destroy()

        buttons = ttk.Frame(content)
        buttons.grid(row=2, column=0, sticky="e", pady=(16, 0))
        if confirmation:
            decline_button = ttk.Button(
                buttons, text="No", command=dialog.destroy
            )
            decline_button.pack(side="left", padx=(0, 8))
            ttk.Button(buttons, text="Yes", command=accept).pack(side="left")
            decline_button.focus_set()
            dialog.bind("<Return>", lambda _event: dialog.destroy())
        else:
            ok_button = ttk.Button(buttons, text="OK", command=accept)
            ok_button.pack(side="left")
            ok_button.focus_set()
            dialog.bind("<Return>", lambda _event: accept())

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        dialog.minsize(max(400, dialog.winfo_reqwidth()), dialog.winfo_reqheight())
        self._center_dialog(dialog, owner)
        owner.wait_window(dialog)
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        return result["accepted"]

    def _show_error(
        self, title: str, message: str, parent: tk.Misc | None = None
    ) -> None:
        self._message_dialog(title, message, kind="error", parent=parent)

    def _show_warning(
        self, title: str, message: str, parent: tk.Misc | None = None
    ) -> None:
        self._message_dialog(title, message, kind="warning", parent=parent)

    def _show_info(
        self, title: str, message: str, parent: tk.Misc | None = None
    ) -> None:
        self._message_dialog(title, message, parent=parent)

    def _ask_yes_no(
        self, title: str, message: str, parent: tk.Misc | None = None
    ) -> bool:
        return self._message_dialog(
            title,
            message,
            kind="warning",
            confirmation=True,
            parent=parent,
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        # Let the match-entry panel keep the height requested by its controls.
        # Giving this row flexible weight can shrink its bottom buttons under
        # Windows display scaling when the history panel also requests space.
        outer.rowconfigure(1, weight=0)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, textvariable=self.heading_var, style="Heading.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Backups", command=self._open_backups).grid(
            row=0, column=1, padx=(12, 3), sticky="e"
        )
        self.settings_button = ttk.Menubutton(header, text="Settings")
        self.settings_menu = tk.Menu(self.settings_button, tearoff=False)
        self.settings_menu.add_radiobutton(
            label="Light theme",
            value="light",
            variable=self.theme_var,
            command=self._select_theme,
        )
        self.settings_menu.add_radiobutton(
            label="Dark theme",
            value="dark",
            variable=self.theme_var,
            command=self._select_theme,
        )
        self.settings_button.configure(menu=self.settings_menu)
        self.settings_button.grid(row=0, column=2, padx=(3, 0), sticky="e")
        self._style_settings_menu()

        league_tools = ttk.Frame(header)
        league_tools.grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Label(league_tools, text="League:").grid(
            row=0, column=0, padx=(0, 5)
        )
        self.league_combo = ttk.Combobox(
            league_tools,
            textvariable=self.league_var,
            state="readonly",
            width=20,
        )
        self.league_combo.grid(row=0, column=1, padx=(0, 5))
        self.league_combo.bind("<<ComboboxSelected>>", self._switch_league)
        ttk.Button(league_tools, text="New", command=self._create_league).grid(
            row=0, column=2, padx=3
        )
        ttk.Button(league_tools, text="Rename", command=self._rename_league).grid(
            row=0, column=3, padx=3
        )
        ttk.Button(
            league_tools, text="Players", command=self._change_player_count
        ).grid(
            row=0, column=4, padx=3
        )
        ttk.Button(league_tools, text="Delete", command=self._delete_league).grid(
            row=0, column=5, padx=3
        )
        ttk.Button(league_tools, text="Settings", command=self._edit_rules).grid(
            row=0, column=6, padx=3
        )
        ttk.Button(
            league_tools, text="Simulator", command=self._open_simulator
        ).grid(row=0, column=7, padx=3)

        standings_frame = ttk.LabelFrame(outer, text="Standings", padding=10)
        standings_frame.grid(
            row=1, column=0, rowspan=2, sticky="nsew", padx=(0, 12)
        )
        standings_frame.rowconfigure(0, weight=1)
        standings_frame.columnconfigure(0, weight=1)

        self.standings = ttk.Treeview(
            standings_frame,
            columns=(
                "rank",
                "player",
                "rating",
                "sb_score",
                "match_record",
                "match_pct",
                "game_record",
                "game_pct",
            ),
            show="headings",
            selectmode="browse",
        )
        headings = {
            "rank": ("#", 40, "center"),
            "player": ("Player", 150, "w"),
            "rating": ("Rating", 85, "e"),
            "sb_score": ("SB", 50, "e"),
            "match_record": ("Match W-D-L", 90, "center"),
            "match_pct": ("Match %", 70, "e"),
            "game_record": ("Game W-L", 80, "center"),
            "game_pct": ("Game %", 70, "e"),
        }
        for column, (label, width, anchor) in headings.items():
            self.standings.heading(column, text=label)
            self.standings.column(column, width=width, anchor=anchor)
        self.standings.grid(row=0, column=0, sticky="nsew")
        standings_scroll = ttk.Scrollbar(
            standings_frame, orient="vertical", command=self.standings.yview
        )
        standings_scroll.grid(row=0, column=1, sticky="ns")
        standings_horizontal_scroll = ttk.Scrollbar(
            standings_frame, orient="horizontal", command=self.standings.xview
        )
        standings_horizontal_scroll.grid(row=1, column=0, sticky="ew")
        self.standings.configure(
            yscrollcommand=standings_scroll.set,
            xscrollcommand=standings_horizontal_scroll.set,
        )

        standings_buttons = ttk.Frame(standings_frame)
        standings_buttons.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        ttk.Button(
            standings_buttons, text="Rename selected player", command=self._rename_player
        ).pack(side="left")
        ttk.Button(
            standings_buttons,
            text="Reset league",
            command=self._reset_league,
        ).pack(side="right")

        match_frame = ttk.LabelFrame(outer, text="Record a match", padding=12)
        match_frame.grid(row=1, column=1, sticky="new")
        match_frame.columnconfigure(1, weight=1)

        ttk.Label(match_frame, text="Player 1 (winner for a win)").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=5
        )
        self.winner_combo = ttk.Combobox(
            match_frame, textvariable=self.winner_var, state="readonly"
        )
        self.winner_combo.grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(match_frame, text="Player 2").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=5
        )
        self.loser_combo = ttk.Combobox(
            match_frame, textvariable=self.loser_var, state="readonly"
        )
        self.loser_combo.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(match_frame, text="Final score").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=5
        )
        self.fixed_score_frame = ttk.Frame(match_frame)
        self.fixed_score_frame.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(
            self.fixed_score_frame, textvariable=self.winner_score_var
        ).pack(side="left", padx=(0, 5))
        self.score_combo = ttk.Combobox(
            self.fixed_score_frame,
            textvariable=self.loser_games_var,
            values=("0", "1", "2"),
            state="readonly",
            width=4,
        )
        self.score_combo.pack(side="left")

        self.custom_score_frame = ttk.Frame(match_frame)
        self.custom_score_frame.grid(row=2, column=1, sticky="w", pady=5)
        self.winner_score_spin = ttk.Spinbox(
            self.custom_score_frame,
            from_=1,
            to=MAX_CUSTOM_SCORE,
            textvariable=self.winner_games_var,
            width=6,
            command=self._update_preview,
        )
        self.winner_score_spin.pack(side="left")
        ttk.Label(self.custom_score_frame, text=" - ").pack(side="left")
        self.loser_score_spin = ttk.Spinbox(
            self.custom_score_frame,
            from_=0,
            to=MAX_CUSTOM_SCORE - 1,
            textvariable=self.loser_games_var,
            width=6,
            command=self._update_preview,
        )
        self.loser_score_spin.pack(side="left")

        actions = ttk.Frame(match_frame)
        actions.grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(10, 4)
        )
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.record_button = ttk.Button(
            actions, text="Record win", command=self._record_match
        )
        self.record_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.draw_button = ttk.Button(
            actions, text="Record draw", command=self._record_draw
        )
        self.draw_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.undo_button = ttk.Button(
            actions, text="Undo last", command=self._undo_last_match
        )
        self.undo_button.grid(row=0, column=2, padx=(6, 0))

        ttk.Separator(match_frame).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Label(
            match_frame,
            textvariable=self.preview_var,
            wraplength=330,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 4))

        for widget in (self.winner_combo, self.loser_combo, self.score_combo):
            widget.bind("<<ComboboxSelected>>", lambda _event: self._update_preview())
        for widget in (self.winner_score_spin, self.loser_score_spin):
            widget.bind("<KeyRelease>", lambda _event: self._update_preview())
            widget.bind("<FocusOut>", lambda _event: self._update_preview())

        activity_notebook = ttk.Notebook(outer)
        activity_notebook.grid(row=2, column=1, sticky="nsew", pady=(12, 0))
        history_frame = ttk.Frame(activity_notebook, padding=8)
        log_frame = ttk.Frame(activity_notebook, padding=8)
        graphs_frame = ttk.Frame(activity_notebook, padding=8)
        activity_notebook.add(history_frame, text="Match history")
        activity_notebook.add(graphs_frame, text="Graphs")
        activity_notebook.add(log_frame, text="Activity log")
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)
        self.history = ttk.Treeview(
            history_frame,
            columns=("time", "result", "change"),
            show="headings",
        )
        self.history.heading("time", text="Time")
        self.history.heading("result", text="Result")
        self.history.heading("change", text="Elo")
        self.history.column("time", width=115, anchor="w")
        self.history.column("result", width=150, anchor="w")
        self.history.column("change", width=75, anchor="e")
        self.history.grid(row=0, column=0, sticky="nsew")
        history_scroll = ttk.Scrollbar(
            history_frame, orient="vertical", command=self.history.yview
        )
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.history.configure(yscrollcommand=history_scroll.set)

        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.activity_log = ttk.Treeview(
            log_frame,
            columns=("time", "league", "action", "details"),
            show="headings",
        )
        for column, label, width in (
            ("time", "Time", 110),
            ("league", "League", 110),
            ("action", "Action", 100),
            ("details", "Details", 260),
        ):
            self.activity_log.heading(column, text=label)
            self.activity_log.column(column, width=width, anchor="w")
        self.activity_log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.activity_log.yview
        )
        log_scroll.grid(row=0, column=1, sticky="ns")
        
        log_scroll_x = ttk.Scrollbar(
            log_frame, orient="horizontal", command=self.activity_log.xview
        )
        log_scroll_x.grid(row=1, column=0, sticky="ew")
        self.activity_log.configure(
            yscrollcommand=log_scroll.set,
            xscrollcommand=log_scroll_x.set
        )

        self._build_graphs_tab(graphs_frame)

        ttk.Label(outer, textvariable=self.status_var, anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_graphs_tab(self, parent) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(controls, text="Player:").pack(side="left")
        self.graph_player_combo = ttk.Combobox(
            controls, state="readonly", width=15
        )
        self.graph_player_combo.pack(side="left", padx=(4, 16))
        self.graph_player_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_graph())
        self.graph_metric_var = tk.StringVar(value="elo")
        for metric, label in (("elo", "Elo"), ("pct", "Win %"), ("sb", "SB Score")):
            rb = ttk.Radiobutton(
                controls,
                text=label,
                value=metric,
                variable=self.graph_metric_var,
                command=self._refresh_graph,
            )
            rb.pack(side="left", padx=4)
        graph_colors = self._graph_colors()
        self.graph_canvas = tk.Canvas(
            parent,
            bg=graph_colors["background"],
            highlightthickness=1,
            highlightbackground=graph_colors["axis"],
        )
        self.graph_canvas.grid(row=1, column=0, sticky="nsew")
        self.graph_canvas.bind("<Configure>", lambda e: self._refresh_graph())

    def _graph_colors(self) -> dict[str, str]:
        colors = THEME_PALETTES[self.theme_var.get()]
        return {
            "background": colors["field"],
            "axis": colors["border"],
            "grid": colors["button_active"],
            "text": colors["muted"],
            "plot": colors["selection"],
        }

    def _refresh_graph(self) -> None:
        if not hasattr(self, "graph_canvas"): return
        graph_colors = self._graph_colors()
        self.graph_canvas.configure(
            background=graph_colors["background"],
            highlightbackground=graph_colors["axis"],
        )
        self.graph_canvas.delete("all")
        width = self.graph_canvas.winfo_width()
        height = self.graph_canvas.winfo_height()
        if width < 50 or height < 50: return

        player_name = self.graph_player_combo.get()
        player_id = self.player_name_to_id.get(player_name)
        if player_id is None: return

        metric = self.graph_metric_var.get()
        matches = self.league.matches

        y_values = []
        if metric == "elo":
            current_elo = 1500.0
            y_values.append(current_elo)
            for m in matches:
                if m.winner_id == player_id:
                    current_elo += m.rating_change
                    y_values.append(current_elo)
                elif m.loser_id == player_id:
                    current_elo -= m.rating_change
                    y_values.append(current_elo)
        elif metric == "pct":
            match_points = 0.0
            total = 0
            y_values.append(0.0)
            for m in matches:
                if m.winner_id == player_id or m.loser_id == player_id:
                    total += 1
                    if m.is_draw:
                        match_points += 0.5
                    elif m.winner_id == player_id:
                        match_points += 1.0
                    y_values.append((match_points / total) * 100)
        elif metric == "sb":
            match_scores = {p.id: 0.0 for p in self.league.players}
            opponent_weights: list[tuple[int, float]] = []
            y_values.append(0.0)
            for m in matches:
                if m.is_draw:
                    match_scores[m.winner_id] += 0.5
                    match_scores[m.loser_id] += 0.5
                    if m.winner_id == player_id:
                        opponent_weights.append((m.loser_id, 0.5))
                    elif m.loser_id == player_id:
                        opponent_weights.append((m.winner_id, 0.5))
                else:
                    match_scores[m.winner_id] += 1.0
                    if m.winner_id == player_id:
                        opponent_weights.append((m.loser_id, 1.0))
                if m.winner_id == player_id or m.loser_id == player_id:
                    sb = sum(
                        match_scores[opponent_id] * weight
                        for opponent_id, weight in opponent_weights
                    )
                    y_values.append(sb)

        if not y_values:
            return

        min_y = min(y_values)
        max_y = max(y_values)
        if min_y == max_y:
            min_y -= 1
            max_y += 1

        margin_x = 45
        margin_y = 20

        self.graph_canvas.create_line(
            margin_x, height - margin_y, width, height - margin_y,
            fill=graph_colors["axis"],
        )
        self.graph_canvas.create_line(
            margin_x, 0, margin_x, height - margin_y,
            fill=graph_colors["axis"],
        )

        for i in range(5):
            y_pos = margin_y + i * (height - 2 * margin_y) / 4
            val = max_y - i * (max_y - min_y) / 4
            self.graph_canvas.create_line(
                margin_x, y_pos, width, y_pos,
                fill=graph_colors["grid"], dash=(4, 4),
            )
            self.graph_canvas.create_text(
                margin_x - 5, y_pos, text=f"{val:.1f}", anchor="e",
                font=("Segoe UI", 8), fill=graph_colors["text"],
            )

        if len(y_values) == 1:
            x = margin_x + (width - margin_x) / 2
            y = margin_y + (max_y - y_values[0]) / (max_y - min_y) * (height - 2 * margin_y)
            self.graph_canvas.create_oval(
                x - 3, y - 3, x + 3, y + 3,
                fill=graph_colors["plot"], outline=graph_colors["plot"],
            )
        else:
            points = []
            for i, val in enumerate(y_values):
                x = margin_x + (i / (len(y_values) - 1)) * (width - margin_x - 10)
                y = margin_y + (max_y - val) / (max_y - min_y) * (height - 2 * margin_y)
                points.extend([x, y])
            self.graph_canvas.create_line(
                points, fill=graph_colors["plot"], width=2
            )

    def _apply_theme(self, theme: str, save: bool = True) -> None:
        if theme not in THEME_PALETTES:
            theme = "light"
            self.theme_var.set(theme)
        colors = THEME_PALETTES[theme]

        self.root.configure(background=colors["background"])
        self.root.option_add("*TCombobox*Listbox.background", colors["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", colors["foreground"])
        self.root.option_add(
            "*TCombobox*Listbox.selectBackground", colors["selection"]
        )
        self.root.option_add(
            "*TCombobox*Listbox.selectForeground", colors["selection_text"]
        )

        self.style.configure(
            ".",
            background=colors["background"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            darkcolor=colors["border"],
            lightcolor=colors["border"],
            troughcolor=colors["background"],
            font=("Segoe UI", 9),
        )
        self.style.configure("TFrame", background=colors["background"])
        self.style.configure("TLabel", background=colors["background"])
        self.style.configure(
            "Heading.TLabel",
            background=colors["background"],
            foreground=colors["foreground"],
            font=("Segoe UI", 16, "bold"),
        )
        self.style.configure(
            "Subheading.TLabel", font=("Segoe UI", 10, "bold")
        )
        self.style.configure(
            "Error.TLabel",
            background=colors["background"],
            foreground="#c42b1c" if theme == "light" else "#ff99a4",
        )
        self.style.configure(
            "Warning.TLabel",
            background=colors["background"],
            foreground="#9d5d00" if theme == "light" else "#fce100",
            font=("Segoe UI", 11, "bold"),
        )
        self.style.configure(
            "Information.TLabel",
            background=colors["background"],
            foreground=colors["selection"],
            font=("Segoe UI", 11, "bold"),
        )
        self.style.configure(
            "Error.TLabel",
            font=("Segoe UI", 11, "bold"),
        )
        self.style.configure(
            "TLabelframe",
            background=colors["background"],
            bordercolor=colors["border"],
        )
        self.style.configure(
            "TLabelframe.Label",
            background=colors["background"],
            foreground=colors["foreground"],
        )
        self.style.configure(
            "TButton",
            background=colors["button"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            padding=(9, 5),
        )
        self.style.map(
            "TButton",
            background=[("active", colors["button_active"])],
            foreground=[("disabled", colors["disabled"])],
        )
        self.style.configure(
            "TMenubutton",
            background=colors["button"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            padding=(9, 5),
        )
        self.style.map(
            "TMenubutton", background=[("active", colors["button_active"])]
        )
        self.style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["foreground"],
            insertcolor=colors["foreground"],
        )
        self.style.configure(
            "TSpinbox",
            fieldbackground=colors["field"],
            foreground=colors["foreground"],
            arrowcolor=colors["foreground"],
            insertcolor=colors["foreground"],
        )
        self.style.configure(
            "TCheckbutton",
            background=colors["background"],
            foreground=colors["foreground"],
        )
        self.style.map(
            "TCheckbutton",
            background=[("active", colors["button_active"])],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            background=colors["button"],
            foreground=colors["foreground"],
            arrowcolor=colors["foreground"],
            bordercolor=colors["border"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["field"])],
            foreground=[("readonly", colors["foreground"])],
            selectbackground=[("readonly", colors["field"])],
            selectforeground=[("readonly", colors["foreground"])],
        )
        self.style.configure(
            "Treeview",
            background=colors["field"],
            fieldbackground=colors["field"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            rowheight=25,
        )
        self.style.map(
            "Treeview",
            background=[("selected", colors["selection"])],
            foreground=[("selected", colors["selection_text"])],
        )
        self.style.configure(
            "Treeview.Heading",
            background=colors["button"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            font=("Segoe UI", 9, "bold"),
        )
        self.style.map(
            "Treeview.Heading", background=[("active", colors["button_active"])]
        )
        self.style.configure("TSeparator", background=colors["border"])
        self._style_settings_menu()
        self.root.after_idle(lambda: self._set_title_bar_theme(self.root))
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.configure(background=colors["background"])
                child.after_idle(lambda window=child: self._set_title_bar_theme(window))
        if hasattr(self, "graph_canvas"):
            self._refresh_graph()

        if save:
            try:
                save_theme(SETTINGS_FILE, theme)
            except (OSError, ValueError) as error:
                self._show_error(
                    "Theme not saved",
                    f"The theme changed for this session but could not be saved.\n\n{error}",
                    parent=self.root,
                )
                self.status_var.set(
                    f"{theme.title()} theme selected for this session; not saved."
                )
            else:
                self.status_var.set(f"{theme.title()} theme selected and saved.")

    def _style_settings_menu(self) -> None:
        if not hasattr(self, "settings_menu"):
            return
        colors = THEME_PALETTES[self.theme_var.get()]
        self.settings_menu.configure(
            background=colors["panel"],
            foreground=colors["foreground"],
            activebackground=colors["selection"],
            activeforeground=colors["selection_text"],
            selectcolor=colors["selection"],
            borderwidth=1,
        )

    def _select_theme(self) -> None:
        theme = self.theme_var.get()
        self._apply_theme(theme)
        try:
            self.audit_log.append(
                "theme_changed",
                self.collection.active.id,
                self.collection.active.name,
                f"Changed the application theme to {theme}.",
            )
        except OSError as error:
            self._show_warning(
                "Activity not logged",
                f"The theme changed, but the activity log could not be updated.\n\n{error}",
                parent=self.root,
            )
        self._refresh_activity_log()

    def _restore_collection(self, state: dict) -> None:
        self.collection = LeagueCollection.from_dict(state)
        self.league = self.collection.active.league

    def _commit_edit(
        self,
        previous_state: dict,
        action: str,
        details: str,
        league_id: str | None = None,
        league_name: str | None = None,
        create_backup: bool = True,
    ) -> None:
        """Save a mutation, optionally backing up its prior state, and audit it."""
        previous = LeagueCollection.from_dict(previous_state)
        try:
            if create_backup:
                self.backups.create(previous, f"before-{action}")
            self.collection.save(DATA_FILE)
            current = self.collection.active
            self.audit_log.append(
                action,
                league_id if league_id is not None else current.id,
                league_name if league_name is not None else current.name,
                details,
            )
        except (OSError, ValueError):
            self._restore_collection(previous_state)
            try:
                self.collection.save(DATA_FILE)
            except OSError:
                pass
            raise

    def _refresh_league_selector(self) -> None:
        names = [item.name for item in self.collection.leagues]
        self.league_name_to_id = {item.name: item.id for item in self.collection.leagues}
        self.league_combo["values"] = names
        self.league_var.set(self.collection.active.name)
        player_count = len(self.collection.active.league.players)
        win_condition = self.collection.active.league.win_condition
        format_name = (
            "Custom Scores"
            if win_condition.score_mode == SCORE_MODE_CUSTOM
            else f"First to {win_condition.games_to_win}"
        )
        self.heading_var.set(f"{player_count}-Player Elo League - {format_name}")
        self.root.title(
            f"{self.collection.active.name} - {player_count}-Player Elo League - "
            f"{format_name}"
        )

    def _refresh_activity_log(self) -> None:
        if not hasattr(self, "activity_log"):
            return
        self.activity_log.delete(*self.activity_log.get_children())
        for entry in reversed(self.audit_log.read(limit=500)):
            timestamp_text = str(entry.get("timestamp", ""))
            try:
                timestamp_text = datetime.fromisoformat(timestamp_text).strftime(
                    "%b %d %H:%M"
                )
            except ValueError:
                pass
            self.activity_log.insert(
                "",
                "end",
                values=(
                    timestamp_text,
                    entry.get("league_name") or "All leagues",
                    str(entry.get("action", "")).replace("_", " ").title(),
                    entry.get("details", ""),
                ),
            )

    def _switch_league(self, _event: tk.Event | None = None) -> None:
        league_id = self.league_name_to_id.get(self.league_var.get())
        if league_id is None or league_id == self.collection.active_league_id:
            return
        previous_state = self.collection.to_dict()
        try:
            self.collection.switch_to(league_id)
            self.league = self.collection.active.league
            self._commit_edit(
                previous_state,
                "league_switched",
                f"Switched to {self.collection.active.name}.",
                create_backup=False,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._show_error("League not switched", str(error), parent=self.root)
        self.player_name_to_id.clear()
        self._refresh_all()

    def _create_league(self) -> None:
        name = self._ask_text(
            "New league",
            "League name:",
            f"League {len(self.collection.leagues) + 1}",
            parent=self.root,
        )
        if name is None:
            return
        player_count = self._ask_integer(
            "New league",
            f"Number of players ({MIN_PLAYER_COUNT}-{MAX_PLAYER_COUNT}):",
            len(self.collection.active.league.players),
            MIN_PLAYER_COUNT,
            MAX_PLAYER_COUNT,
            parent=self.root,
        )
        if player_count is None:
            return
        previous_state = self.collection.to_dict()
        try:
            created = self.collection.create_league(name, player_count)
            self.league = created.league
            self._commit_edit(
                previous_state,
                "league_created",
                f"Created {created.name} with {player_count} players at 1500.00 Elo.",
                created.id,
                created.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._show_error("League not created", str(error), parent=self.root)
            return
        self.player_name_to_id.clear()
        self.status_var.set(f"Created and switched to {created.name}.")
        self._refresh_all()

    def _rename_league(self) -> None:
        current = self.collection.active
        name = self._ask_text(
            "Rename league",
            "League name:",
            current.name,
            parent=self.root,
        )
        if name is None:
            return
        previous_state = self.collection.to_dict()
        try:
            old_name, new_name = self.collection.rename_league(current.id, name)
            self._commit_edit(
                previous_state,
                "league_renamed",
                f"Renamed league from {old_name} to {new_name}.",
                current.id,
                new_name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._show_error("League not renamed", str(error), parent=self.root)
            return
        self.status_var.set(f"Renamed league to {new_name}.")
        self._refresh_all()

    def _open_simulator(self) -> None:
        if self.league.win_condition.score_mode != SCORE_MODE_FIXED:
            self._show_info(
                "League simulator",
                "The simulator supports First to N leagues only. Change this "
                "league's match format in League Settings before simulating.",
                parent=self.root,
            )
            return

        maximum = simulation_limit(
            len(self.league.players), self.league.win_condition.games_to_win
        )
        dialog = tk.Toplevel(self.root)
        dialog.title("First-to-N League Simulator")
        dialog.geometry("850x610")
        dialog.minsize(700, 500)
        self._configure_dialog(dialog, self.root, resizable=(True, True))
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        ttk.Label(
            dialog,
            text=(
                f"Simulate a single round-robin where every player meets once "
                f"in First to {self.league.win_condition.games_to_win}. Game "
                "probabilities use current Elo. Simulated Elo changes use this "
                "league's K-factor, rounding, and score multipliers. Saved "
                "ratings and results change only if Apply One Season is selected."
            ),
            wraplength=790,
            justify="left",
        ).grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")

        controls = ttk.Frame(dialog)
        controls.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        controls.columnconfigure(5, weight=1)
        ttk.Label(controls, text="Simulations:").grid(
            row=0, column=0, padx=(0, 5)
        )
        simulations_var = tk.IntVar(value=min(2_000, maximum))
        ttk.Spinbox(
            controls,
            from_=1,
            to=maximum,
            textvariable=simulations_var,
            width=9,
        ).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(controls, text=f"Maximum: {maximum:,}").grid(
            row=0, column=2, padx=(0, 16)
        )
        ttk.Label(controls, text="Random seed (optional):").grid(
            row=0, column=3, padx=(0, 5)
        )
        seed_var = tk.StringVar()
        ttk.Entry(controls, textvariable=seed_var, width=12).grid(
            row=0, column=4, padx=(0, 12)
        )
        status_var = tk.StringVar(value="Choose the run size, then select Simulate.")
        ttk.Label(controls, textvariable=status_var).grid(
            row=1, column=0, columnspan=6, pady=(8, 0), sticky="w"
        )

        results_frame = ttk.Frame(dialog)
        results_frame.grid(row=2, column=0, padx=14, sticky="nsew")
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)
        results_tree = ttk.Treeview(
            results_frame,
            columns=(
                "rank",
                "player",
                "title_probability",
                "average_rank",
                "average_match_record",
                "average_game_record",
            ),
            show="headings",
        )
        for column, label, width, anchor in (
            ("rank", "#", 45, "center"),
            ("player", "Player", 180, "w"),
            ("title_probability", "Title %", 85, "e"),
            ("average_rank", "Avg Rank", 85, "e"),
            ("average_match_record", "Avg Match W-L", 130, "center"),
            ("average_game_record", "Avg Game W-L", 130, "center"),
        ):
            results_tree.heading(column, text=label)
            results_tree.column(column, width=width, anchor=anchor)
        results_tree.grid(row=0, column=0, sticky="nsew")
        vertical_scroll = ttk.Scrollbar(
            results_frame, orient="vertical", command=results_tree.yview
        )
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll = ttk.Scrollbar(
            results_frame, orient="horizontal", command=results_tree.xview
        )
        horizontal_scroll.grid(row=1, column=0, sticky="ew")
        results_tree.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )

        buttons = ttk.Frame(dialog)
        buttons.grid(row=3, column=0, padx=14, pady=14, sticky="e")

        def run_simulation() -> None:
            try:
                simulations = simulations_var.get()
                seed_text = seed_var.get().strip()
                seed = int(seed_text) if seed_text else None
            except (ValueError, tk.TclError):
                self._show_error(
                    "Invalid simulator input",
                    "Simulations and random seed must be whole numbers.",
                    parent=dialog,
                )
                return

            run_button.configure(state="disabled")
            dialog.configure(cursor="wait")
            status_var.set(
                f"Running {simulations:,} simulated round-robin seasons..."
            )
            dialog.update_idletasks()
            try:
                result = simulate_first_to_n_league(
                    self.league, simulations, seed
                )
            except ValueError as error:
                self._show_error(
                    "Simulation not run", str(error), parent=dialog
                )
                return
            finally:
                dialog.configure(cursor="")
                run_button.configure(state="normal")

            results_tree.delete(*results_tree.get_children())
            for rank, player_result in enumerate(result.players, start=1):
                results_tree.insert(
                    "",
                    "end",
                    values=(
                        rank,
                        player_result.name,
                        f"{player_result.title_probability:.1f}%",
                        f"{player_result.average_rank:.2f}",
                        f"{player_result.average_matches_won:.1f}-"
                        f"{player_result.average_matches_lost:.1f}",
                        f"{player_result.average_games_won:.1f}-"
                        f"{player_result.average_games_lost:.1f}",
                    ),
                )
            status_var.set(
                f"Completed {result.simulations:,} seasons; "
                f"{result.matches_per_simulation} matches per season."
            )
            self.status_var.set(
                f"Completed a {result.simulations:,}-season simulation for "
                f"{self.collection.active.name}."
            )

        def apply_simulated_season() -> None:
            try:
                seed_text = seed_var.get().strip()
                seed = int(seed_text) if seed_text else None
                simulated_matches = simulate_first_to_n_season(
                    self.league, seed
                )
            except (ValueError, tk.TclError) as error:
                self._show_error(
                    "Invalid simulator input", str(error), parent=dialog
                )
                return

            match_count = len(simulated_matches)
            if not self._ask_yes_no(
                "Apply simulated season?",
                f"Add {match_count} simulated round-robin matches to "
                f"{self.collection.active.name}?\n\n"
                "This updates ratings, standings, graphs, and match history. "
                "An automatic backup will be created first.",
                parent=dialog,
            ):
                return

            previous_state = self.collection.to_dict()
            current = self.collection.active
            try:
                for match in simulated_matches:
                    self.league.record_match(
                        match.winner_id,
                        match.loser_id,
                        match.loser_games,
                        match.winner_games,
                    )
                seed_description = str(seed) if seed is not None else "random"
                self._commit_edit(
                    previous_state,
                    "simulation_applied",
                    f"Applied one simulated round-robin season "
                    f"({match_count} matches; seed: {seed_description}).",
                    current.id,
                    current.name,
                )
            except (OSError, ValueError) as error:
                self._restore_collection(previous_state)
                self._refresh_all()
                self._show_error(
                    "Simulation not applied",
                    f"The league was not changed.\n\n{error}",
                    parent=dialog,
                )
                return

            self._refresh_all()
            self.status_var.set(
                f"Applied {match_count} simulated matches to {current.name}."
            )
            dialog.destroy()

        run_button = ttk.Button(
            buttons, text="Simulate", command=run_simulation
        )
        run_button.pack(side="left", padx=(0, 8))
        ttk.Button(
            buttons,
            text="Apply One Season",
            command=apply_simulated_season,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(
            side="left"
        )
        dialog.bind("<Return>", lambda _event: run_simulation())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._center_dialog(dialog, self.root)

    def _edit_rules(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("League Settings")
        dialog.geometry("480x700")
        dialog.minsize(440, 580)
        self._configure_dialog(
            dialog, self.root, resizable=(True, True)
        )
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(4, weight=1)

        colors = THEME_PALETTES[self.theme_var.get()]
        dialog.configure(background=colors["background"])

        format_frame = ttk.LabelFrame(dialog, text="Match format", padding=10)
        format_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        format_frame.columnconfigure(1, weight=1)
        ttk.Label(format_frame, text="Format:").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        format_labels = {
            "First to N": SCORE_MODE_FIXED,
            "Custom scores": SCORE_MODE_CUSTOM,
        }
        current_format_label = (
            "Custom scores"
            if self.league.win_condition.score_mode == SCORE_MODE_CUSTOM
            else "First to N"
        )
        format_var = tk.StringVar(value=current_format_label)
        format_combo = ttk.Combobox(
            format_frame,
            textvariable=format_var,
            state="readonly",
            values=tuple(format_labels),
            width=18,
        )
        format_combo.grid(row=0, column=1, sticky="w")
        format_combo.set(current_format_label)
        format_help = ttk.Label(format_frame, wraplength=370, justify="left")
        format_help.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        fixed_frame = ttk.LabelFrame(dialog, text="First-to-N settings", padding=10)
        fixed_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        fixed_frame.columnconfigure(1, weight=1)
        ttk.Label(fixed_frame, text="Games to win:").grid(
            row=0, column=0, padx=(0, 8), pady=(0, 5), sticky="w"
        )
        games_var = tk.IntVar(value=self.league.win_condition.games_to_win)
        ttk.Spinbox(
            fixed_frame,
            from_=1,
            to=MAX_GAMES_TO_WIN,
            textvariable=games_var,
            width=6,
        ).grid(row=0, column=1, pady=(0, 5), sticky="w")

        elo_frame = ttk.LabelFrame(dialog, text="Elo settings", padding=10)
        elo_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        elo_frame.columnconfigure(1, weight=1)
        ttk.Label(elo_frame, text="K-factor:").grid(
            row=0, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        k_factor_var = tk.StringVar(value=f"{self.league.k_factor:g}")
        ttk.Entry(
            elo_frame, textvariable=k_factor_var, width=10
        ).grid(row=0, column=1, pady=3, sticky="w")
        ttk.Label(elo_frame, text="Elo decimal places:").grid(
            row=1, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        decimal_places_var = tk.IntVar(
            value=self.league.elo_decimal_places
        )
        ttk.Spinbox(
            elo_frame,
            from_=0,
            to=MAX_ELO_DECIMAL_PLACES,
            textvariable=decimal_places_var,
            width=6,
        ).grid(row=1, column=1, pady=3, sticky="w")
        ttk.Label(
            elo_frame,
            text=(
                f"K-factor range: {MIN_K_FACTOR:g}-{MAX_K_FACTOR:g}. "
                "Each transferred Elo change is rounded to the selected "
                "number of decimal places."
            ),
            wraplength=410,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        calc_elo_var = tk.BooleanVar(value=self.league.calculate_elo)
        allow_draws_var = tk.BooleanVar(value=self.league.allow_draws)
        options_frame = ttk.Frame(dialog)
        options_frame.grid(row=3, column=0, padx=12, pady=5, sticky="w")
        ttk.Checkbutton(
            options_frame, text="Auto-calculate Elo", variable=calc_elo_var
        ).pack(side="left")
        ttk.Checkbutton(
            options_frame, text="Allow draws", variable=allow_draws_var
        ).pack(side="left", padx=(16, 0))

        mult_frame = ttk.LabelFrame(dialog, text="Score Multipliers", padding=10)
        mult_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        mult_frame.rowconfigure(0, weight=1)
        mult_frame.columnconfigure(0, weight=1)
        
        canvas = tk.Canvas(mult_frame, borderwidth=0, highlightthickness=0, background=colors["background"])
        scrollbar = ttk.Scrollbar(mult_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        mult_vars = {}
        for i in range(MAX_GAMES_TO_WIN):
            mult_vars[i] = tk.StringVar(value=str(self.league.win_condition.score_multipliers.get(i, 1.0)))

        def update_mults(*_args):
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            try:
                g = games_var.get()
            except tk.TclError:
                return
            if not 1 <= g <= MAX_GAMES_TO_WIN:
                return
            for i in range(g):
                ttk.Label(scrollable_frame, text=f"Loser scores {i}:").grid(row=i, column=0, sticky="w", pady=2)
                ttk.Entry(scrollable_frame, textvariable=mult_vars[i], width=8).grid(row=i, column=1, sticky="w", pady=2)

        def update_format(*_args):
            if format_labels.get(format_var.get()) == SCORE_MODE_CUSTOM:
                fixed_frame.grid_remove()
                mult_frame.grid_remove()
                format_help.configure(
                    text="Enter both final scores for each match. A shutout uses "
                    "100% of the Elo change; the closest possible win uses 50%; "
                    "other margins scale proportionally."
                )
            else:
                fixed_frame.grid()
                mult_frame.grid()
                format_help.configure(
                    text="The winner reaches the fixed target. Set the Elo margin "
                    "multiplier for every possible losing score."
                )

        games_var.trace_add("write", update_mults)
        format_var.trace_add("write", update_format)
        update_mults()
        update_format()

        def save():
            try:
                score_mode = format_labels.get(format_var.get())
                if score_mode is None:
                    raise ValueError("Select a valid match format.")
                if score_mode == SCORE_MODE_CUSTOM:
                    current_rules = self.league.win_condition
                    new_rules = WinCondition(
                        games_to_win=current_rules.games_to_win,
                        score_multipliers=dict(current_rules.score_multipliers),
                        score_mode=score_mode,
                    )
                else:
                    games_to_win = games_var.get()
                    if not 1 <= games_to_win <= MAX_GAMES_TO_WIN:
                        raise ValueError(
                            f"Games to win must be between 1 and {MAX_GAMES_TO_WIN}."
                        )
                    new_mults = {
                        score: float(mult_vars[score].get())
                        for score in range(games_to_win)
                    }
                    new_rules = WinCondition(
                        games_to_win=games_to_win,
                        score_multipliers=new_mults,
                        score_mode=score_mode,
                    )
                new_k_factor = validate_k_factor(float(k_factor_var.get()))
                new_decimal_places = validate_elo_decimal_places(
                    decimal_places_var.get()
                )
                if new_decimal_places is None:
                    raise ValueError(
                        "League Elo decimal places cannot be unlimited."
                    )
            except (ValueError, tk.TclError) as error:
                self._show_error("Invalid input", str(error), parent=dialog)
                return
                
            previous_state = self.collection.to_dict()
            self.league.win_condition = new_rules
            self.league.calculate_elo = calc_elo_var.get()
            self.league.k_factor = new_k_factor
            self.league.elo_decimal_places = new_decimal_places
            self.league.allow_draws = allow_draws_var.get()
            try:
                format_name = (
                    "custom scores"
                    if score_mode == SCORE_MODE_CUSTOM
                    else f"first to {new_rules.games_to_win}"
                )
                self._commit_edit(
                    previous_state,
                    "rules_edited",
                    f"Set {self.collection.active.name} to {format_name}; "
                    f"K={new_k_factor:g}; Elo rounding={new_decimal_places} "
                    f"decimal places; automatic Elo "
                    f"{'on' if calc_elo_var.get() else 'off'}; "
                    f"draws {'allowed' if allow_draws_var.get() else 'disabled'}.",
                )
            except (OSError, ValueError) as e:
                self._restore_collection(previous_state)
                self._show_error("Rules not saved", str(e), parent=dialog)
                return
            
            self._refresh_all()
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=5, column=0, padx=10, pady=10, sticky="e")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Save", command=save).pack(side="left")
        self._center_dialog(dialog, self.root)

    def _change_player_count(self) -> None:
        current = self.collection.active
        old_count = len(self.league.players)
        player_count = self._ask_integer(
            "Player count",
            f"Number of players for {current.name} "
            f"({MIN_PLAYER_COUNT}-{MAX_PLAYER_COUNT}):",
            old_count,
            MIN_PLAYER_COUNT,
            MAX_PLAYER_COUNT,
            parent=self.root,
        )
        if player_count is None or player_count == old_count:
            return

        if player_count < old_count:
            removed_players = self.league.players[player_count:]
            removed_ids = {player.id for player in removed_players}
            affected_matches = sum(
                match.winner_id in removed_ids or match.loser_id in removed_ids
                for match in self.league.matches
            )
            visible_names = ", ".join(player.name for player in removed_players[:8])
            if len(removed_players) > 8:
                visible_names += f", and {len(removed_players) - 8} more"
            if not self._ask_yes_no(
                "Reduce player count",
                f"Reduce {current.name} from {old_count} to {player_count} players?\n\n"
                f"Players removed from the end of the roster: {visible_names}\n"
                f"Matches removed: {affected_matches}\n\n"
                "Remaining matches will be replayed to recalculate accurate Elo "
                "ratings. An automatic backup will be created first.",
                parent=self.root,
            ):
                return

        previous_state = self.collection.to_dict()
        try:
            result = self.league.resize_players(player_count)
            if player_count > old_count:
                details = (
                    f"Increased roster from {old_count} to {player_count}; "
                    f"added {', '.join(result['added'])}."
                )
            else:
                details = (
                    f"Reduced roster from {old_count} to {player_count}; removed "
                    f"{', '.join(result['removed'])} and "
                    f"{result['removed_match_count']} related matches; "
                    "recalculated retained results."
                )
            self._commit_edit(
                previous_state,
                "player_count_changed",
                details,
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._show_error(
                "Player count not changed", str(error), parent=self.root
            )
            return

        self.player_name_to_id.clear()
        self.status_var.set(
            f"{current.name} now has {player_count} players."
        )
        self._refresh_all()

    def _delete_league(self) -> None:
        current = self.collection.active
        if not self._ask_yes_no(
            "Delete league",
            f"Delete {current.name} and all of its match history?\n\n"
            "An automatic backup will be created first. The activity log will remain.",
            parent=self.root,
        ):
            return
        previous_state = self.collection.to_dict()
        try:
            deleted = self.collection.delete_league(current.id)
            self.league = self.collection.active.league
            self._commit_edit(
                previous_state,
                "league_deleted",
                f"Deleted {deleted.name}; a pre-delete backup is available.",
                deleted.id,
                deleted.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._show_error("League not deleted", str(error), parent=self.root)
            return
        self.player_name_to_id.clear()
        self.status_var.set(
            f"Deleted {deleted.name}; switched to {self.collection.active.name}."
        )
        self._refresh_all()

    def _open_backups(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Backups")
        window.geometry("720x420")
        window.minsize(580, 320)
        self._configure_dialog(
            window, self.root, resizable=(True, True)
        )
        colors = THEME_PALETTES[self.theme_var.get()]
        window.configure(background=colors["background"])

        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="Automatic backups are created before every saved edit. "
            "The newest 50 are retained.",
            wraplength=650,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        tree = ttk.Treeview(
            frame,
            columns=("time", "reason", "file"),
            show="headings",
            selectmode="browse",
        )
        for column, label, width in (
            ("time", "Created", 150),
            ("reason", "Reason", 210),
            ("file", "Backup file", 300),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        backup_items: dict[str, object] = {}

        def refresh() -> None:
            tree.delete(*tree.get_children())
            backup_items.clear()
            for index, backup in enumerate(self.backups.list()):
                item_id = str(index)
                backup_items[item_id] = backup
                created = backup.created_at
                try:
                    created = datetime.fromisoformat(created).strftime("%b %d, %Y %H:%M:%S")
                except ValueError:
                    pass
                tree.insert(
                    "", "end", iid=item_id,
                    values=(created, backup.reason, backup.path.name),
                )

        def create_now() -> None:
            try:
                backup = self.backups.create(self.collection, "manual-backup")
            except OSError as error:
                self._show_error("Backup not created", str(error), parent=window)
                return
            active = self.collection.active
            try:
                self.audit_log.append(
                    "backup_created",
                    active.id,
                    active.name,
                    f"Created manual backup {backup.path.name}.",
                )
            except OSError as error:
                self._show_warning(
                    "Activity not logged",
                    f"The backup was created, but the activity log could not be "
                    f"updated.\n\n{error}",
                    parent=window,
                )
            self.status_var.set("Manual backup created.")
            refresh()
            self._refresh_activity_log()

        def restore_selected() -> None:
            selection = tree.selection()
            if not selection:
                self._show_info(
                    "Restore backup", "Select a backup first.", parent=window
                )
                return
            backup = backup_items[selection[0]]
            if not self._ask_yes_no(
                "Restore backup",
                f"Restore {backup.path.name}?\n\n"
                "All leagues will return to that snapshot. The current database "
                "will be backed up first, and the activity log will remain.",
                parent=window,
            ):
                return
            previous_state = self.collection.to_dict()
            try:
                restored = self.backups.restore(backup)
                self.collection = restored
                self.league = restored.active.league
                self._commit_edit(
                    previous_state,
                    "backup_restored",
                    f"Restored all leagues from {backup.path.name}.",
                )
            except (OSError, ValueError) as error:
                self._restore_collection(previous_state)
                self._show_error("Backup not restored", str(error), parent=window)
                return
            self.player_name_to_id.clear()
            self.status_var.set(f"Restored backup {backup.path.name}.")
            self._refresh_all()
            window.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="Create backup now", command=create_now).pack(
            side="left"
        )
        ttk.Button(buttons, text="Restore selected", command=restore_selected).pack(
            side="right"
        )
        ttk.Button(buttons, text="Close", command=window.destroy).pack(
            side="right", padx=(0, 8)
        )
        refresh()
        self._center_dialog(window, self.root)

    def _refresh_all(self) -> None:
        self._refresh_league_selector()
        selected_winner_id = self.player_name_to_id.get(self.winner_var.get())
        selected_loser_id = self.player_name_to_id.get(self.loser_var.get())

        names = [player.name for player in self.league.players]
        self.player_name_to_id = {
            player.name: player.id for player in self.league.players
        }
        self.winner_combo["values"] = names
        self.loser_combo["values"] = names
        
        win_condition = self.league.win_condition
        if win_condition.score_mode == SCORE_MODE_CUSTOM:
            self.fixed_score_frame.grid_remove()
            self.custom_score_frame.grid()
            try:
                winner_games = int(self.winner_games_var.get())
                loser_games = int(self.loser_games_var.get())
                win_condition.get_multiplier(loser_games, winner_games)
            except ValueError:
                self.winner_games_var.set(str(win_condition.games_to_win))
                self.loser_games_var.set("0")
        else:
            self.custom_score_frame.grid_remove()
            self.fixed_score_frame.grid()
            self.winner_games_var.set(str(win_condition.games_to_win))
            self.winner_score_var.set(f"{win_condition.games_to_win} -")
            valid_scores = tuple(
                str(i) for i in sorted(win_condition.score_multipliers.keys())
            )
            self.score_combo["values"] = valid_scores
            if self.loser_games_var.get() not in valid_scores:
                self.loser_games_var.set(valid_scores[0] if valid_scores else "0")

        if selected_winner_id is not None:
            self.winner_var.set(self.league.player(selected_winner_id).name)
        elif names:
            self.winner_var.set(names[0])
        if selected_loser_id is not None:
            self.loser_var.set(self.league.player(selected_loser_id).name)
        elif len(names) > 1:
            self.loser_var.set(names[1])

        self._refresh_standings()
        self._refresh_history()
        self._refresh_activity_log()
        if hasattr(self, "graph_player_combo"):
            self.graph_player_combo["values"] = names
            if self.graph_player_combo.get() not in names and names:
                self.graph_player_combo.set(names[0])
            self._refresh_graph()

        self._update_preview()
        self.undo_button.configure(
            state="normal" if self.league.matches else "disabled"
        )

    def _format_elo(self, value: float) -> str:
        return f"{value:.{self.league.elo_decimal_places}f}"

    def _format_signed_elo(self, value: float) -> str:
        return f"{value:+.{self.league.elo_decimal_places}f}"

    def _refresh_standings(self) -> None:
        selected = self.standings.selection()
        selected_id = int(selected[0]) if selected else None
        self.standings.delete(*self.standings.get_children())
        statistics = self.league.statistics()
        ranked_players = sorted(
            self.league.players,
            key=lambda player: (
                -player.rating,
                -statistics[player.id].sb_score,
                player.name.casefold(),
            ),
        )
        for rank, player in enumerate(ranked_players, start=1):
            stats = statistics[player.id]
            self.standings.insert(
                "",
                "end",
                iid=str(player.id),
                values=(
                    rank,
                    player.name,
                    self._format_elo(player.rating),
                    f"{stats.sb_score:.1f}",
                    f"{stats.matches_won}-{stats.matches_drawn}-{stats.matches_lost}",
                    f"{stats.match_win_percentage:.1f}%",
                    f"{stats.games_won}-{stats.games_lost}",
                    f"{stats.game_win_percentage:.1f}%",
                ),
            )
        if selected_id is not None and self.standings.exists(str(selected_id)):
            self.standings.selection_set(str(selected_id))

    def _refresh_history(self) -> None:
        self.history.delete(*self.history.get_children())
        for match in reversed(self.league.matches):
            winner = self.league.player(match.winner_id).name
            loser = self.league.player(match.loser_id).name
            try:
                timestamp = datetime.fromisoformat(match.timestamp).strftime("%b %d %H:%M")
            except ValueError:
                timestamp = match.timestamp
            result = (
                f"{winner} drew with {loser}"
                if match.is_draw
                else f"{winner} {match.winner_games}-{match.loser_games} {loser}"
            )
            elo_change = (
                f"{self._format_signed_elo(match.rating_change)}/"
                f"{self._format_signed_elo(-match.rating_change)}"
                if match.is_draw
                else f"+/-{self._format_elo(match.rating_change)}"
            )
            self.history.insert(
                "",
                "end",
                values=(
                    timestamp,
                    result,
                    elo_change,
                ),
            )

    def _selected_match(self) -> tuple[int, int, int, int]:
        winner_id = self.player_name_to_id.get(self.winner_var.get())
        loser_id = self.player_name_to_id.get(self.loser_var.get())
        if winner_id is None or loser_id is None:
            raise ValueError("Select both a winner and a loser.")
        try:
            winner_games = int(self.winner_games_var.get())
            loser_games = int(self.loser_games_var.get())
        except ValueError as error:
            raise ValueError("Final scores must be whole numbers.") from error
        self.league.win_condition.get_multiplier(loser_games, winner_games)
        return winner_id, loser_id, winner_games, loser_games

    def _selected_players(self) -> tuple[int, int]:
        player_one_id = self.player_name_to_id.get(self.winner_var.get())
        player_two_id = self.player_name_to_id.get(self.loser_var.get())
        if player_one_id is None or player_two_id is None:
            raise ValueError("Select both players.")
        if player_one_id == player_two_id:
            raise ValueError("The two players must be different.")
        return player_one_id, player_two_id

    def _update_preview(self) -> None:
        try:
            winner_id, loser_id, winner_games, loser_games = self._selected_match()
            preview = self.league.preview_match(
                winner_id, loser_id, loser_games, winner_games
            )
            draw_preview = (
                self.league.preview_draw(winner_id, loser_id)
                if self.league.allow_draws
                else None
            )
            winner = self.league.player(winner_id)
            loser = self.league.player(loser_id)
        except ValueError as error:
            self.preview_var.set(str(error))
            self.record_button.configure(state="disabled")
            try:
                self._selected_players()
            except ValueError:
                self.draw_button.configure(state="disabled")
            else:
                self.draw_button.configure(
                    state="normal" if self.league.allow_draws else "disabled"
                )
            return

        preview_text = (
            f"Margin multiplier: {preview['multiplier']:.0%}\n"
            f"Expected chance: {winner.name} {preview['winner_expected']:.1%}, "
            f"{loser.name} {preview['loser_expected']:.1%}\n"
            f"Change: +/-{self._format_elo(preview['change'])} Elo\n"
            f"New ratings: {winner.name} "
            f"{self._format_elo(preview['winner_after'])}, "
            f"{loser.name} {self._format_elo(preview['loser_after'])}"
        )
        if draw_preview is not None:
            preview_text += (
                f"\nDraw Elo: {winner.name} "
                f"{self._format_signed_elo(draw_preview['change'])}, "
                f"{loser.name} "
                f"{self._format_signed_elo(-draw_preview['change'])}"
            )
        else:
            preview_text += "\nDraws are disabled for this league."
        self.preview_var.set(preview_text)
        self.record_button.configure(state="normal")
        self.draw_button.configure(
            state="normal" if self.league.allow_draws else "disabled"
        )

    def _record_match(self) -> None:
        previous_state = self.collection.to_dict()
        current = self.collection.active
        try:
            winner_id, loser_id, winner_games, loser_games = self._selected_match()
            match = self.league.record_match(
                winner_id, loser_id, loser_games, winner_games
            )
            winner = self.league.player(match.winner_id).name
            loser = self.league.player(match.loser_id).name
            stats = self.league.statistics()
            winner_sb = stats[match.winner_id].sb_score
            loser_sb = stats[match.loser_id].sb_score
            self._commit_edit(
                previous_state,
                "match_recorded",
                f"{winner} defeated {loser} "
                f"{match.winner_games}-{loser_games}; transferred "
                f"{self._format_elo(match.rating_change)} Elo "
                f"(SB: {winner} {winner_sb:.1f}, {loser} {loser_sb:.1f}).",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            self._show_error("Match not recorded", str(error), parent=self.root)
            return

        self.status_var.set(
            f"Saved: {winner} defeated {loser} "
            f"{match.winner_games}-{loser_games}; "
            f"+/-{self._format_elo(match.rating_change)} Elo"
        )
        self._refresh_all()

    def _record_draw(self) -> None:
        previous_state = self.collection.to_dict()
        current = self.collection.active
        try:
            player_one_id, player_two_id = self._selected_players()
            match = self.league.record_draw(player_one_id, player_two_id)
            player_one = self.league.player(match.winner_id).name
            player_two = self.league.player(match.loser_id).name
            stats = self.league.statistics()
            self._commit_edit(
                previous_state,
                "draw_recorded",
                f"{player_one} drew with {player_two}; "
                f"Elo changes: {player_one} "
                f"{self._format_signed_elo(match.rating_change)}, "
                f"{player_two} "
                f"{self._format_signed_elo(-match.rating_change)} "
                f"(SB: {player_one} {stats[match.winner_id].sb_score:.1f}, "
                f"{player_two} {stats[match.loser_id].sb_score:.1f}).",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            self._show_error("Draw not recorded", str(error), parent=self.root)
            return

        self.status_var.set(
            f"Saved: {player_one} drew with {player_two}; "
            f"Elo {self._format_signed_elo(match.rating_change)} / "
            f"{self._format_signed_elo(-match.rating_change)}"
        )
        self._refresh_all()

    def _undo_last_match(self) -> None:
        if not self.league.matches:
            return
        match = self.league.matches[-1]
        winner = self.league.player(match.winner_id).name
        loser = self.league.player(match.loser_id).name
        result = (
            f"{winner} drew with {loser}"
            if match.is_draw
            else f"{winner} {match.winner_games}-{match.loser_games} {loser}"
        )
        if not self._ask_yes_no(
            "Undo last match",
            f"Undo {result}?",
            parent=self.root,
        ):
            return
        previous_state = self.collection.to_dict()
        current = self.collection.active
        try:
            self.league.undo_last_match()
            stats = self.league.statistics()
            winner_sb = stats[match.winner_id].sb_score
            loser_sb = stats[match.loser_id].sb_score
            self._commit_edit(
                previous_state,
                "match_undone",
                f"Undid {result}; restored the prior ratings "
                f"(SB: {winner} {winner_sb:.1f}, {loser} {loser_sb:.1f}).",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            self._show_error("Match not undone", str(error), parent=self.root)
            return
        self.status_var.set("The last match was undone and the ratings were restored.")
        self._refresh_all()

    def _rename_player(self) -> None:
        selected = self.standings.selection()
        if not selected:
            self._show_info(
                "Rename player", "Select a player in the standings first.", parent=self.root
            )
            return
        player = self.league.player(int(selected[0]))
        new_name = self._ask_text(
            "Rename player",
            "Player name:",
            player.name,
            parent=self.root,
        )
        if new_name is None:
            return
        previous_state = self.collection.to_dict()
        current = self.collection.active
        old_name = player.name
        try:
            self.league.rename_player(player.id, new_name)
            saved_name = self.league.player(player.id).name
            self._commit_edit(
                previous_state,
                "player_renamed",
                f"Renamed player from {old_name} to {saved_name}.",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            self._show_error("Player not renamed", str(error), parent=self.root)
            return
        self.status_var.set(f"Renamed player to {self.league.player(player.id).name}.")
        self._refresh_all()

    def _reset_league(self) -> None:
        if not self._ask_yes_no(
            "Reset league",
            f"Reset all ratings to {self._format_elo(INITIAL_RATING)} and "
            "permanently clear every match "
            "result?\n\nPlayer names and the selected theme will be preserved.",
            parent=self.root,
        ):
            return

        previous_state = self.collection.to_dict()
        current = self.collection.active
        cleared_matches = len(self.league.matches)
        try:
            self.league.reset_standings()
            self._commit_edit(
                previous_state,
                "league_reset",
                f"Reset all ratings to {self._format_elo(INITIAL_RATING)} and "
                f"cleared {cleared_matches} matches.",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            self._show_error("League not reset", str(error), parent=self.root)
            return

        self.status_var.set(
            "League reset: all ratings are "
            f"{self._format_elo(INITIAL_RATING)} and match history is empty."
        )
        self._refresh_all()

    def _on_close(self) -> None:
        # Every mutation is saved immediately. Avoid overwriting an unreadable
        # save file merely because the user opened and closed the program.
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    instance_lock = ApplicationInstanceLock(LOCK_FILE)
    try:
        if not instance_lock.acquire():
            root.withdraw()
            messagebox.showwarning(
                "Elo League Calculator is already running",
                "Close the other Elo League Calculator window before opening "
                "another one.",
                parent=root,
            )
            return
        EloCalculatorApp(root)
        root.mainloop()
    finally:
        instance_lock.release()
        try:
            root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()


# Purpose: Tkinter desktop interface for configuring and operating Elo leagues.
# Upstream: elo_model.py and elo_storage.py provide rules, persistence, and backups.
# Upstream purpose: Validate league data and preserve user changes safely.
# Environment: Python 3.10+ with Tkinter on Windows.
# Generated: 2026-09-03 08:31 America/New_York.
# Changes: Adds a backed-up simulator-to-league action and makes graph canvas,
# axes, grid, labels, and plots follow the active light or dark theme.
