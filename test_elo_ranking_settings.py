# test_elo_ranking_settings.py
# Request: Review ranking settings, build a verified package and publish it.
"""Regression coverage for schema migration and the real ranking-settings dialog."""

from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from elo_calculator import EloCalculatorApp, THEME_PALETTES
from elo_model import League, LEAGUE_SCHEMA_VERSION
from elo_storage import LeagueCollection, BackupManager, AuditLog


class RankingPersistenceTests(unittest.TestCase):
    def test_schema_eight_migrates_without_losing_existing_ranking_settings(self):
        for mode in (None, "competition", "dense"):
            data = League.new(3).to_dict()
            data["schema_version"] = 8
            if mode is None:
                data.pop("ranking_mode")
            else:
                data["ranking_mode"] = mode
                data["tiebreaker_hierarchy"] = ["match_pct"]
            league = League.from_dict(data)
            self.assertEqual(league.ranking_mode, mode or "sequential")
            self.assertEqual(league.tiebreaker_hierarchy, data["tiebreaker_hierarchy"])
            self.assertEqual(league.to_dict()["schema_version"], LEAGUE_SCHEMA_VERSION)
            self.assertEqual(LEAGUE_SCHEMA_VERSION, 9)

    def test_ranking_modes_round_trip_and_invalid_values_are_rejected(self):
        for mode in ("sequential", "competition", "dense"):
            league = League.new(3)
            league.ranking_mode = mode
            self.assertEqual(League.from_dict(league.to_dict()).ranking_mode, mode)
        for mode in (None, [], {}, 1, "unknown"):
            with self.subTest(mode=mode):
                data = League.new(3).to_dict()
                data["ranking_mode"] = mode
                with self.assertRaisesRegex(ValueError, "invalid league settings"):
                    League.from_dict(data)


class TkRankingSettingsTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display/library unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data_file = Path(self.directory.name) / "leagues.json"
        self.app = object.__new__(EloCalculatorApp)
        self.app.root = self.root
        self.app.collection = LeagueCollection.new()
        self.app.league = self.app.collection.active.league
        self.app.theme_var = tk.StringVar(self.root, value="dark")
        self.app.backups = BackupManager(Path(self.directory.name) / "backups")
        self.app.audit_log = AuditLog(Path(self.directory.name) / "audit.jsonl")
        self.app._set_title_bar_theme = Mock()
        self.app._refresh_all = Mock()
        self.app._show_error = Mock()
        self.app._show_warning = Mock()
        self.app._show_league_settings()
        self.window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(self.window))
        self.combo = next(w for w in widgets if isinstance(w, ttk.Combobox))
        self.listbox = next(w for w in widgets if isinstance(w, tk.Listbox))
        self.save = next(w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Save Settings")

    def test_save_persists_backs_up_and_audits_the_active_collection(self):
        before = self.app.collection.to_dict()
        self.combo.set("competition")
        with patch("elo_calculator.DATA_FILE", self.data_file):
            self.save.invoke()
        restored = LeagueCollection.load(self.data_file)
        self.assertEqual(restored.active.league.ranking_mode, "competition")
        self.assertEqual(len(restored.leagues), len(before["leagues"]))
        self.assertTrue(list((Path(self.directory.name) / "backups").glob("*.json")))
        self.assertEqual(self.app.audit_log.read()[-1]["action"], "ranking_edited")
        self.app._show_error.assert_not_called()
        self.app._refresh_all.assert_called_once()
        self.assertFalse(self.window.winfo_exists())

    def test_save_failure_restores_state_and_keeps_dialog_open(self):
        before = self.app.collection.to_dict()
        self.combo.set("dense")
        with patch.object(LeagueCollection, "save", side_effect=OSError("disk unavailable")):
            self.save.invoke()
        self.assertEqual(self.app.collection.to_dict(), before)
        self.assertTrue(self.window.winfo_exists())
        self.app._show_error.assert_called_once()
        self.app._refresh_all.assert_not_called()

    def test_recovery_block_also_rolls_back_ranking_settings(self):
        before = self.app.collection.to_dict()
        self.app.data_save_block_reason = "Original save has not been preserved"
        self.combo.set("dense")
        self.save.invoke()
        self.assertEqual(self.app.collection.to_dict(), before)
        self.app._show_error.assert_called_once()
        self.assertFalse(self.data_file.exists())

    def test_dialog_uses_dark_palette_and_fits_its_controls(self):
        self.window.update_idletasks()
        colors = THEME_PALETTES["dark"]
        self.assertEqual(self.listbox.cget("background"), colors["field"])
        self.assertEqual(self.listbox.cget("foreground"), colors["foreground"])
        self.assertEqual(self.window.cget("background"), colors["background"])
        self.assertGreaterEqual(self.window.minsize()[1], self.window.winfo_reqheight())


if __name__ == "__main__":
    unittest.main()

# Purpose: Protect ranking persistence, rollback, schema migration and dialog theme.
# Upstream: elo_calculator.py edits leagues; elo_storage.py saves/backs up/audits;
# elo_model.py validates and versions saved settings. Python 3.12 / Windows Tk 8.6.
# Generated: 2026-09-15 America/New_York. Changes: New regression-test file.
