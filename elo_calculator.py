"""Tkinter desktop interface for the twelve-player Elo calculator."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from elo_model import (
    DEFAULT_PLAYER_COUNT,
    MAX_PLAYER_COUNT,
    MIN_PLAYER_COUNT,
    SCORE_MULTIPLIERS,
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
                lambda: messagebox.showwarning(
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
            "match_record": ("Match W-L", 80, "center"),
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

        ttk.Label(match_frame, text="Winner").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=5
        )
        self.winner_combo = ttk.Combobox(
            match_frame, textvariable=self.winner_var, state="readonly"
        )
        self.winner_combo.grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(match_frame, text="Loser").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=5
        )
        self.loser_combo = ttk.Combobox(
            match_frame, textvariable=self.loser_var, state="readonly"
        )
        self.loser_combo.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(match_frame, text="Final score").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=5
        )
        score_frame = ttk.Frame(match_frame)
        score_frame.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(score_frame, text="3 –").pack(side="left", padx=(0, 5))
        self.score_combo = ttk.Combobox(
            score_frame,
            textvariable=self.loser_games_var,
            values=("0", "1", "2"),
            state="readonly",
            width=4,
        )
        self.score_combo.pack(side="left")

        actions = ttk.Frame(match_frame)
        actions.grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(10, 4)
        )
        actions.columnconfigure(0, weight=1)
        self.record_button = ttk.Button(
            actions, text="Record match", command=self._record_match
        )
        self.record_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.undo_button = ttk.Button(
            actions, text="Undo last", command=self._undo_last_match
        )
        self.undo_button.grid(row=0, column=1, padx=(6, 0))

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

        activity_notebook = ttk.Notebook(outer)
        activity_notebook.grid(row=2, column=1, sticky="nsew", pady=(12, 0))
        history_frame = ttk.Frame(activity_notebook, padding=8)
        log_frame = ttk.Frame(activity_notebook, padding=8)
        activity_notebook.add(history_frame, text="Match history")
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
        self.activity_log.configure(yscrollcommand=log_scroll.set)

        ttk.Label(outer, textvariable=self.status_var, anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0)
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

        if save:
            try:
                save_theme(SETTINGS_FILE, theme)
            except (OSError, ValueError) as error:
                messagebox.showerror(
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
            messagebox.showwarning(
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
        self.heading_var.set(f"{player_count}-Player Elo League")
        self.root.title(
            f"{self.collection.active.name} — {player_count}-Player Elo League"
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
            messagebox.showerror("League not switched", str(error), parent=self.root)
        self.player_name_to_id.clear()
        self._refresh_all()

    def _create_league(self) -> None:
        name = simpledialog.askstring(
            "New league",
            "League name:",
            initialvalue=f"League {len(self.collection.leagues) + 1}",
            parent=self.root,
        )
        if name is None:
            return
        player_count = simpledialog.askinteger(
            "New league",
            f"Number of players ({MIN_PLAYER_COUNT}-{MAX_PLAYER_COUNT}):",
            initialvalue=len(self.collection.active.league.players),
            minvalue=MIN_PLAYER_COUNT,
            maxvalue=MAX_PLAYER_COUNT,
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
            messagebox.showerror("League not created", str(error), parent=self.root)
            return
        self.player_name_to_id.clear()
        self.status_var.set(f"Created and switched to {created.name}.")
        self._refresh_all()

    def _rename_league(self) -> None:
        current = self.collection.active
        name = simpledialog.askstring(
            "Rename league",
            "League name:",
            initialvalue=current.name,
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
            messagebox.showerror("League not renamed", str(error), parent=self.root)
            return
        self.status_var.set(f"Renamed league to {new_name}.")
        self._refresh_all()

    def _change_player_count(self) -> None:
        current = self.collection.active
        old_count = len(self.league.players)
        player_count = simpledialog.askinteger(
            "Player count",
            f"Number of players for {current.name} "
            f"({MIN_PLAYER_COUNT}-{MAX_PLAYER_COUNT}):",
            initialvalue=old_count,
            minvalue=MIN_PLAYER_COUNT,
            maxvalue=MAX_PLAYER_COUNT,
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
            if not messagebox.askyesno(
                "Reduce player count",
                f"Reduce {current.name} from {old_count} to {player_count} players?\n\n"
                f"Players removed from the end of the roster: {visible_names}\n"
                f"Matches removed: {affected_matches}\n\n"
                "Remaining matches will be replayed to recalculate accurate Elo "
                "ratings. An automatic backup will be created first.",
                icon="warning",
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
            messagebox.showerror("Player count not changed", str(error), parent=self.root)
            return

        self.player_name_to_id.clear()
        self.status_var.set(
            f"{current.name} now has {player_count} players."
        )
        self._refresh_all()

    def _delete_league(self) -> None:
        current = self.collection.active
        if not messagebox.askyesno(
            "Delete league",
            f"Delete {current.name} and all of its match history?\n\n"
            "An automatic backup will be created first. The activity log will remain.",
            icon="warning",
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
            messagebox.showerror("League not deleted", str(error), parent=self.root)
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
        window.transient(self.root)
        window.grab_set()
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
                messagebox.showerror("Backup not created", str(error), parent=window)
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
                messagebox.showwarning(
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
                messagebox.showinfo(
                    "Restore backup", "Select a backup first.", parent=window
                )
                return
            backup = backup_items[selection[0]]
            if not messagebox.askyesno(
                "Restore backup",
                f"Restore {backup.path.name}?\n\n"
                "All leagues will return to that snapshot. The current database "
                "will be backed up first, and the activity log will remain.",
                icon="warning",
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
                messagebox.showerror("Backup not restored", str(error), parent=window)
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
        self._update_preview()
        self.undo_button.configure(
            state="normal" if self.league.matches else "disabled"
        )

    def _refresh_standings(self) -> None:
        selected = self.standings.selection()
        selected_id = int(selected[0]) if selected else None
        self.standings.delete(*self.standings.get_children())
        statistics = self.league.statistics()
        ranked_players = sorted(
            self.league.players, key=lambda player: (-player.rating, player.name.casefold())
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
                    f"{player.rating:.2f}",
                    f"{stats.matches_won}-{stats.matches_lost}",
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
            self.history.insert(
                "",
                "end",
                values=(
                    timestamp,
                    f"{winner} 3–{match.loser_games} {loser}",
                    f"±{match.rating_change:.2f}",
                ),
            )

    def _selected_match(self) -> tuple[int, int, int]:
        winner_id = self.player_name_to_id.get(self.winner_var.get())
        loser_id = self.player_name_to_id.get(self.loser_var.get())
        if winner_id is None or loser_id is None:
            raise ValueError("Select both a winner and a loser.")
        try:
            loser_games = int(self.loser_games_var.get())
        except ValueError as error:
            raise ValueError("Select a valid final score.") from error
        if loser_games not in SCORE_MULTIPLIERS:
            raise ValueError("Select a valid final score.")
        return winner_id, loser_id, loser_games

    def _update_preview(self) -> None:
        try:
            winner_id, loser_id, loser_games = self._selected_match()
            preview = self.league.preview_match(winner_id, loser_id, loser_games)
            winner = self.league.player(winner_id)
            loser = self.league.player(loser_id)
        except ValueError as error:
            self.preview_var.set(str(error))
            self.record_button.configure(state="disabled")
            return

        self.preview_var.set(
            f"Margin multiplier: {preview['multiplier']:.0%}\n"
            f"Expected chance: {winner.name} {preview['winner_expected']:.1%}, "
            f"{loser.name} {preview['loser_expected']:.1%}\n"
            f"Change: ±{preview['change']:.2f} Elo\n"
            f"New ratings: {winner.name} {preview['winner_after']:.2f}, "
            f"{loser.name} {preview['loser_after']:.2f}"
        )
        self.record_button.configure(state="normal")

    def _record_match(self) -> None:
        previous_state = self.collection.to_dict()
        current = self.collection.active
        try:
            winner_id, loser_id, loser_games = self._selected_match()
            match = self.league.record_match(winner_id, loser_id, loser_games)
            winner = self.league.player(match.winner_id).name
            loser = self.league.player(match.loser_id).name
            self._commit_edit(
                previous_state,
                "match_recorded",
                f"{winner} defeated {loser} 3-{loser_games}; transferred "
                f"{match.rating_change:.4f} Elo.",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            messagebox.showerror("Match not recorded", str(error), parent=self.root)
            return

        self.status_var.set(
            f"Saved: {winner} defeated {loser} 3–{loser_games}; "
            f"±{match.rating_change:.2f} Elo"
        )
        self._refresh_all()

    def _undo_last_match(self) -> None:
        if not self.league.matches:
            return
        match = self.league.matches[-1]
        winner = self.league.player(match.winner_id).name
        loser = self.league.player(match.loser_id).name
        if not messagebox.askyesno(
            "Undo last match",
            f"Undo {winner} 3–{match.loser_games} {loser}?",
            parent=self.root,
        ):
            return
        previous_state = self.collection.to_dict()
        current = self.collection.active
        try:
            self.league.undo_last_match()
            self._commit_edit(
                previous_state,
                "match_undone",
                f"Undid {winner} 3-{match.loser_games} {loser}; restored the prior ratings.",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            messagebox.showerror("Match not undone", str(error), parent=self.root)
            return
        self.status_var.set("The last match was undone and the ratings were restored.")
        self._refresh_all()

    def _rename_player(self) -> None:
        selected = self.standings.selection()
        if not selected:
            messagebox.showinfo(
                "Rename player", "Select a player in the standings first.", parent=self.root
            )
            return
        player = self.league.player(int(selected[0]))
        new_name = simpledialog.askstring(
            "Rename player",
            "Player name:",
            initialvalue=player.name,
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
            messagebox.showerror("Player not renamed", str(error), parent=self.root)
            return
        self.status_var.set(f"Renamed player to {self.league.player(player.id).name}.")
        self._refresh_all()

    def _reset_league(self) -> None:
        if not messagebox.askyesno(
            "Reset league",
            "Reset all ratings to 1500.00 and permanently clear every match "
            "result?\n\nPlayer names and the selected theme will be preserved.",
            icon="warning",
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
                f"Reset all ratings to 1500.00 and cleared {cleared_matches} matches.",
                current.id,
                current.name,
            )
        except (OSError, ValueError) as error:
            self._restore_collection(previous_state)
            self._refresh_all()
            messagebox.showerror("League not reset", str(error), parent=self.root)
            return

        self.status_var.set(
            "League reset: all ratings are 1500.00 and match history is empty."
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
