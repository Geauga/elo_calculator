# test_elo_bracket.py
# Request: Verify progressing double-elimination brackets, persistence and undo.
"""Tournament invariants across every supported field and final outcome."""

from collections import Counter
import random
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from elo_bracket import build_bracket
from elo_model import League
from elo_calculator import EloCalculatorApp, THEME_PALETTES, _playoff_seeds
from elo_storage import LeagueCollection


class BracketEngineTests(unittest.TestCase):
    def test_all_sizes_require_two_losses_and_finish_with_correct_match_count(self):
        for size in range(2, 65):
            for seed in (17, 41):
                with self.subTest(size=size, seed=seed):
                    rng = random.Random(seed)
                    results, losses = [], Counter()
                    bracket = build_bracket(list(range(size)), "double")
                    while bracket.champion is None:
                        self.assertTrue(bracket.ready)
                        match = rng.choice(bracket.ready)
                        first, second = match.players
                        self.assertLess(losses[first], 2)
                        self.assertLess(losses[second], 2)
                        winner, loser = (first, second) if rng.randrange(2) else (second, first)
                        results.append((match.id, winner, loser, 3, 1))
                        losses[loser] += 1
                        bracket = build_bracket(list(range(size)), "double", results)
                        self.assertLessEqual(len(results), 2 * size - 1)
                    self.assertFalse(bracket.ready)
                    self.assertLess(losses[bracket.champion], 2)
                    self.assertTrue(all(losses[p] == 2 for p in range(size) if p != bracket.champion))
                    reset = next(m for m in bracket.matches if m.id == "F2-1")
                    self.assertEqual(len(results), 2 * size - 1 if reset.status == "complete" else 2 * size - 2)

    def test_reset_is_required_only_when_lower_finalist_wins_first_final(self):
        bracket = build_bracket([0, 1], "double", [("W1-1", 0, 1, 3, 0)])
        self.assertEqual([m.id for m in bracket.ready], ["F1-1"])
        upper = build_bracket([0, 1], "double", [("W1-1", 0, 1, 3, 0), ("F1-1", 0, 1, 3, 0)])
        self.assertEqual(upper.champion, 0)
        self.assertEqual(upper.matches[-1].status, "not_needed")
        results = [("W1-1", 0, 1, 3, 0), ("F1-1", 1, 0, 3, 2)]
        lower = build_bracket([0, 1], "double", results)
        self.assertIsNone(lower.champion)
        self.assertEqual([m.id for m in lower.ready], ["F2-1"])
        for winner, loser in ((0, 1), (1, 0)):
            self.assertEqual(build_bracket([0, 1], "double", results + [("F2-1", winner, loser, 3, 1)]).champion, winner)

    def test_single_elimination_finishes_with_n_minus_one_results(self):
        for size in range(2, 65):
            results = []
            bracket = build_bracket(list(range(size)))
            while bracket.champion is None:
                match = bracket.ready[0]
                results.append((match.id, *match.players, 3, 0))
                bracket = build_bracket(list(range(size)), results=results)
            self.assertEqual(len(results), size - 1)

    def test_invalid_out_of_order_duplicate_and_wrong_player_results_are_rejected(self):
        for results in ([("F1-1", 0, 1, 3, 0)], [("W1-1", 0, 2, 3, 0)],
                        [("W1-1", 0, 1, 3, 0)] * 2,
                        [("W1-1", 0, 1, 3, 0), ("F1-1", 0, 1, 3, 0), ("F2-1", 0, 1, 3, 0)]):
            with self.assertRaises(ValueError):
                build_bracket([0, 1], "double", results)


class BracketPersistenceTests(unittest.TestCase):
    def league(self, size=4):
        league = League.new(size)
        league.playoff_size = size
        league.playoff_format = "double"
        return league

    def test_save_reload_frozen_seeds_rated_elo_and_regular_statistics(self):
        league = self.league()
        league.playoffs_rated = True
        seeds = [p.id for p in _playoff_seeds(league)]
        first = league.playoff_bracket(seeds).ready[0]
        winner, loser = reversed(first.players)
        league.record_bracket_match(first.id, winner, 1, seed_ids=seeds)
        self.assertNotEqual(league.player(winner).rating, 1500)
        restored = League.from_dict(league.to_dict())
        self.assertEqual(restored.playoff_seed_ids, seeds)
        self.assertEqual(restored.playoff_bracket(), league.playoff_bracket())
        self.assertEqual(restored.statistics()[winner].matches_won, 0)
        self.assertEqual(restored.matches[0].playoff_match_id, first.id)

    def test_undo_final_reopens_reset_and_first_result_unlocks_seeding(self):
        league = self.league(2)
        for key, winner in (("W1-1", 0), ("F1-1", 1), ("F2-1", 0)):
            league.record_bracket_match(key, winner, 0, seed_ids=[0, 1])
        self.assertEqual(league.playoff_bracket().champion, 0)
        league.undo_last_match()
        self.assertEqual([m.id for m in league.playoff_bracket().ready], ["F2-1"])
        league.undo_last_match()
        league.undo_last_match()
        self.assertEqual(league.playoff_seed_ids, [])

    def test_roster_growth_preserves_started_field_reload_and_progress(self):
        for format_name in ("single", "double"):
            with self.subTest(format=format_name):
                league = self.league()
                league.playoff_size = 8
                league.playoff_format = format_name
                league.record_bracket_match("W1-1", 0, 0, seed_ids=[0, 1, 2, 3])
                before = league.playoff_bracket()
                league.resize_players(5)
                restored = League.from_dict(league.to_dict())
                self.assertEqual(restored.playoff_size, 8)
                self.assertEqual(restored.playoff_seed_ids, [0, 1, 2, 3])
                self.assertEqual(restored.playoff_bracket(), before)
                while restored.playoff_bracket().champion is None:
                    node = restored.playoff_bracket().ready[0]
                    self.assertNotIn(4, node.players)
                    restored.record_bracket_match(node.id, node.players[0], 0)
                    restored = League.from_dict(restored.to_dict())
                restored.resize_players(4)
                self.assertEqual(League.from_dict(restored.to_dict()).playoff_seed_ids,
                                 [0, 1, 2, 3])

    def test_new_bracket_still_requires_full_configured_field(self):
        league = self.league()
        before = league.to_dict()
        with self.assertRaises(ValueError):
            league.record_bracket_match("W1-1", 0, 0, seed_ids=[0, 1])
        self.assertEqual(league.to_dict(), before)
        for seeds in ([0], [0, 1, 2, 3, 4]):
            data = self.league(5).to_dict()
            data["playoff_size"] = 4
            data["playoff_seed_ids"] = seeds
            with self.assertRaises(ValueError):
                League.from_dict(data)

    def test_generic_playoff_results_do_not_advance_bracket(self):
        league = self.league(2)
        league.record_match(0, 1, 0, is_playoff=True)
        league.record_draw(0, 1, is_playoff=True)
        self.assertEqual([m.id for m in league.playoff_bracket([0, 1]).ready], ["W1-1"])

    def test_invalid_inputs_are_atomic_and_bad_saved_routes_are_rejected(self):
        league = self.league(2)
        for key, winner, score, seeds in (("F1-1", 0, 0, [0, 1]), ("W1-1", 4, 0, [0, 1]),
                                          ("W1-1", 0, 3, [0, 1]), ("W1-1", 0, 0, [0, 0])):
            before = league.to_dict()
            with self.assertRaises(ValueError):
                league.record_bracket_match(key, winner, score, seed_ids=seeds)
            self.assertEqual(league.to_dict(), before)
        league.record_bracket_match("W1-1", 0, 0, seed_ids=[0, 1])
        data = league.to_dict()
        data["matches"][0]["playoff_match_id"] = "F1-1"
        with self.assertRaises(ValueError):
            League.from_dict(data)

    def test_old_schema_defaults_single_and_new_format_is_validated(self):
        data = League.new().to_dict()
        data["schema_version"] = 11
        data.pop("playoff_format")
        data.pop("playoff_seed_ids")
        self.assertEqual(League.from_dict(data).playoff_format, "single")
        for value in (None, [], 3, "unknown"):
            data["playoff_format"] = value
            with self.assertRaises(ValueError):
                League.from_dict(data)

    def test_reset_and_removed_seed_clear_bracket_links_but_keep_retained_results(self):
        league = self.league()
        league.record_bracket_match("W1-1", 0, 0, seed_ids=[0, 1, 2, 3])
        league.record_bracket_match("W1-2", 1, 0)
        league.resize_players(3)
        self.assertFalse(league.playoff_seed_ids)
        self.assertTrue(all(not m.playoff_match_id for m in league.matches))
        self.assertEqual(len(league.matches), 1)
        league.reset_standings()
        self.assertFalse(league.matches)
        self.assertEqual(league.playoff_format, "double")

    def test_failed_save_rolls_back_results_seeds_and_ratings(self):
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        app.league = app.collection.active.league
        app.league.playoff_size = 2
        app.league.playoff_format = "double"
        before = app.collection.to_dict()
        app._commit_edit = Mock(side_effect=OSError("disk full"))
        with self.assertRaises(OSError):
            app._save_bracket_result("W1-1", 0, 3, 0, [0, 1])
        self.assertEqual(app.collection.to_dict(), before)


class TkBracketTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()
        self.directory = TemporaryDirectory()
        folder = Path(self.directory.name)
        self.data_path = folder / "leagues.json"
        self.paths = patch.multiple("elo_calculator", DATA_FILE=self.data_path,
                                    SETTINGS_FILE=folder / "settings.json", BACKUP_DIRECTORY=folder / "backups",
                                    AUDIT_LOG_FILE=folder / "audit.jsonl", RECOVERY_DIRECTORY=folder / "recovery")
        self.paths.start()
        self.app = EloCalculatorApp(self.root)
        self.app.league.playoff_size = 4
        self.app.league.playoff_format = "double"
        self.app._refresh_all()

    def tearDown(self):
        if hasattr(self, "app"):
            self.root.update_idletasks()
            self.root.destroy()
            self.paths.stop()
            self.directory.cleanup()

    def descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self.descendants(child)

    def test_result_controls_save_reload_and_undo(self):
        app = self.app
        app._show_bracket_result()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        button = next(w for w in self.descendants(dialog)
                      if isinstance(w, ttk.Button) and w.cget("text") == "Record result")
        button.invoke()
        restored = LeagueCollection.load(self.data_path).active.league
        self.assertEqual(restored.matches[-1].playoff_match_id, "W1-1")
        self.assertEqual(restored.playoff_seed_ids, [0, 1, 2, 3])
        self.assertEqual(app.audit_log.read()[-1]["action"], "bracket_result_recorded")
        self.assertTrue(list((Path(self.directory.name) / "backups").glob("*.json")))
        self.assertNotIn("W1-1", app.bracket_ready_choices.values())
        app.league.undo_last_match()
        app._refresh_all()
        self.assertIn("W1-1", app.bracket_ready_choices.values())
        app._show_league_settings()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        format_combo = next(w for w in self.descendants(dialog) if isinstance(w, ttk.Combobox)
                            and "Double elimination" in w.cget("values"))
        format_combo.set("Single elimination")
        save = next(w for w in self.descendants(dialog)
                    if isinstance(w, ttk.Button) and w.cget("text") == "Save Settings")
        save.invoke()
        self.assertEqual(LeagueCollection.load(self.data_path).active.league.playoff_format, "single")

    def test_scroll_theme_large_field_and_active_format_change_guard(self):
        app = self.app
        app.league.playoff_size = 64
        app.league.resize_players(64)
        for theme in ("dark", "light"):
            app.theme_var.set(theme)
            app._apply_theme(theme, save=False)
            self.root.update_idletasks()
            self.assertEqual(app.playoffs_canvas.cget("background"), THEME_PALETTES[theme]["background"])
            bounds = [float(x) for x in app.playoffs_canvas.cget("scrollregion").split()]
            self.assertGreater(bounds[2], 2000)
            self.assertGreater(bounds[3], 3000)
        app.league.playoff_size = 4
        app._save_bracket_result("W1-1", 0, 3, 0, [0, 1, 2, 3])
        app._show_league_settings()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        combo = next(w for w in self.descendants(dialog) if isinstance(w, ttk.Combobox)
                     and "Double elimination" in w.cget("values"))
        combo.set("Single elimination")
        save = next(w for w in self.descendants(dialog)
                    if isinstance(w, ttk.Button) and w.cget("text") == "Save Settings")
        with patch.object(app, "_show_error") as error:
            save.invoke()
            error.assert_called_once()
        self.assertEqual(app.league.playoff_format, "double")
        dialog.destroy()

    def test_roster_growth_saves_started_bracket_and_next_result(self):
        app = self.app
        app.league.resize_players(4)
        app.league.playoff_size = 8
        app._save_bracket_result("W1-1", 0, 3, 0, [0, 1, 2, 3])
        with patch.object(app, "_ask_integer", return_value=5), \
                patch.object(app, "_show_error") as error:
            app._change_player_count()
            error.assert_not_called()
        restored = LeagueCollection.load(self.data_path).active.league
        self.assertEqual(len(restored.players), 5)
        self.assertEqual(restored.playoff_seed_ids, [0, 1, 2, 3])
        app._save_bracket_result("W1-2", 1, 3, 0, restored.playoff_seed_ids)
        self.assertEqual(len(LeagueCollection.load(self.data_path).active.league.matches), 2)


# Purpose: Verify tournament elimination, byes, reset finals and save/undo safety.
# Upstream: elo_bracket.py routes results; elo_model.py persists them; GUI backs
# up, saves and audits edits. Python 3.12 / Windows Tk 8.6, isolated test data.
# Generated: 2026-10-01 America/New_York. Changes: New regression suite.
# Review update: 2026-10-02 17:57 America/New_York; Python 3.12 / Windows Tk 8.6.
# Purpose: Reproduce and prevent unreadable saves/progress after roster growth.
# Upstream: elo_model.py freezes entrants; GUI roster/results persist the league.
# Upstream purpose: Allow roster edits without modifying an active tournament.
# Changed lines: 108-143 growth/reload/progress and initial-field validation;
# 283-296 real-Tk roster edit, database reload and subsequent bracket result.
