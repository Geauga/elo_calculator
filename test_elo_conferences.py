# test_elo_conferences.py
# Request: Add optional conferences for player grouping and standings, off by default.
"""Conference defaults, persistence, standings and real-dialog regressions."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from elo_calculator import EloCalculatorApp, _ranked_players, _build_season_report
from elo_model import League, LEAGUE_SCHEMA_VERSION
from elo_storage import LeagueCollection, BackupManager, AuditLog


class ConferenceTests(unittest.TestCase):
    def test_conferences_are_off_for_new_and_legacy_leagues(self):
        league = League.new(3)
        self.assertFalse(league.conferences_enabled)
        self.assertEqual(league.conference_names(), [])
        for version in (2, 7, 8, 9):
            data = league.to_dict()
            data['schema_version'] = version
            data.pop('conferences_enabled')
            for player in data['players']:
                player.pop('conference')
            restored = League.from_dict(data)
            self.assertFalse(restored.conferences_enabled)
            self.assertTrue(all(p.conference == '' for p in restored.players))
            self.assertEqual(restored.to_dict()['schema_version'], LEAGUE_SCHEMA_VERSION)

    def test_assignments_round_trip_and_survive_disabling(self):
        league = League.new(3)
        league.configure_conferences(True, {0: ' East ', 1: 'east', 2: ''})
        self.assertEqual([p.conference for p in league.players], ['East', 'East', ''])
        for enabled in (True, False, True):
            league.configure_conferences(enabled, {p.id: p.conference for p in league.players})
            restored = League.from_dict(league.to_dict())
            self.assertEqual(restored.to_dict(), league.to_dict())
            self.assertEqual(restored.conference_names(), ['East'])

    def test_invalid_settings_do_not_partially_change_league(self):
        league = League.new(2)
        league.configure_conferences(True, {0: 'East', 1: 'West'})
        before = league.to_dict()
        for enabled, assignments in ((1, {0: '', 1: ''}), (True, {0: ''}),
                                     (True, {0: 'New', 1: None}),
                                     (True, {0: 'New', 1: 'x' * 41}),
                                     (True, {0: 'New', 1: 'a\nb'}),
                                     (True, {False: 'East', 1: 'West'})):
            with self.subTest(enabled=enabled, assignments=assignments):
                with self.assertRaises(ValueError):
                    league.configure_conferences(enabled, assignments)
                self.assertEqual(league.to_dict(), before)

    def test_saved_invalid_conference_fields_are_rejected(self):
        for enabled in (None, 0, 'false', []):
            data = League.new(2).to_dict()
            data['conferences_enabled'] = enabled
            with self.assertRaises(ValueError):
                League.from_dict(data)
        for name in (None, 5, ['East'], 'x' * 41):
            data = League.new(2).to_dict()
            data['players'][0]['conference'] = name
            with self.assertRaises(ValueError):
                League.from_dict(data)

    def test_memberships_follow_ids_through_rename_resize_and_reset(self):
        league = League.new(3)
        league.configure_conferences(True, {0: 'East', 1: 'West', 2: 'East'})
        league.rename_player(0, 'Renamed')
        league.record_match(0, 1, 0)
        league.resize_players(2)
        self.assertEqual([p.conference for p in league.players], ['East', 'West'])
        league.resize_players(4)
        self.assertEqual([p.conference for p in league.players], ['East', 'West', '', ''])
        league.reset_standings()
        self.assertTrue(league.conferences_enabled)
        self.assertEqual([p.conference for p in league.players], ['East', 'West', '', ''])

    def test_conferences_do_not_change_elo_or_overall_ranking(self):
        plain = League.new(4)
        grouped = deepcopy(plain)
        grouped.configure_conferences(True, {0: 'East', 1: 'West', 2: 'East', 3: ''})
        for league in (plain, grouped):
            league.record_match(0, 1, 0)
            league.record_draw(1, 2)
        for first, second in zip(plain.to_dict()['matches'], grouped.to_dict()['matches']):
            first.pop('timestamp')
            second.pop('timestamp')
            self.assertEqual(first, second)
        self.assertEqual([p.rating for p in plain.players], [p.rating for p in grouped.players])
        self.assertEqual([(r, p.id) for r, p in _ranked_players(plain)],
                         [(r, p.id) for r, p in _ranked_players(grouped)])

    def test_conference_ranks_honor_sharing_and_exclude_other_players(self):
        league = League.new(4)
        league.tiebreaker_hierarchy = ['rating']
        league.players[3].rating = 1400
        for mode, expected in (('sequential', [1, 2, 3]), ('competition', [1, 1, 3]), ('dense', [1, 1, 2])):
            league.ranking_mode = mode
            ranked = _ranked_players(league, player_ids={0, 2, 3})
            self.assertEqual([r for r, _ in ranked], expected)
            self.assertEqual([p.id for _, p in ranked], [0, 2, 3])
        self.assertEqual(_ranked_players(league, player_ids=set()), [])

    def test_simulated_schedule_is_unchanged(self):
        from elo_simulator import simulate_first_to_n_season
        league = League.new(4)
        before = simulate_first_to_n_season(league, seed=27)
        league.configure_conferences(True, {0: 'East', 1: 'West', 2: 'East', 3: 'West'})
        self.assertEqual(simulate_first_to_n_season(league, seed=27), before)

    def test_conferences_are_independent_between_leagues(self):
        collection = LeagueCollection.new()
        first = collection.active.league
        first.configure_conferences(True, {p.id: 'East' for p in first.players})
        second = collection.create_league('Second', 2).league
        self.assertFalse(second.conferences_enabled)
        self.assertEqual(second.conference_names(), [])
        restored = LeagueCollection.from_dict(collection.to_dict())
        self.assertTrue(restored.leagues[0].league.conferences_enabled)
        self.assertFalse(restored.leagues[1].league.conferences_enabled)

    def test_reports_only_add_conference_standings_when_enabled(self):
        league = League.new(3)
        def report():
            return _build_season_report('Test', '2026-09-24', league)
        self.assertNotIn('Conference Standings', report())
        league.configure_conferences(True, {0: 'East', 1: 'West', 2: ''})
        self.assertIn('Conference: East', report())
        self.assertIn('Conference: West', report())
        self.assertIn('Unassigned players', report())
        league.conferences_enabled = False
        self.assertNotIn('Conference Standings', report())


class TkConferenceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Tk unavailable: {error}')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = object.__new__(EloCalculatorApp)
        self.app.root = self.root
        self.app.collection = LeagueCollection.new()
        self.app.collection.active.league = League.new(3)
        self.app.league = self.app.collection.active.league
        self.app.theme_var = tk.StringVar(self.root, value='dark')
        self.app._set_title_bar_theme = Mock()
        self.app._refresh_all = Mock()
        self.app._show_error = Mock()
        self.app._show_warning = Mock()
        self.app.backups = BackupManager(Path(self.directory.name) / 'backups')
        self.app.audit_log = AuditLog(Path(self.directory.name) / 'audit.jsonl')

    def open_dialog(self):
        self.app._show_conference_settings()
        self.window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        widgets = list(descendants(self.window))
        self.enabled = next(w for w in widgets if isinstance(w, ttk.Checkbutton))
        self.roster = next(w for w in widgets if isinstance(w, ttk.Treeview))
        self.entry = next(w for w in widgets if isinstance(w, ttk.Combobox))
        self.save = next(w for w in widgets if isinstance(w, ttk.Button) and w.cget('text') == 'Save conferences')
        self.cancel = next(w for w in widgets if isinstance(w, ttk.Button) and w.cget('text') == 'Cancel')
        self.root.update()

    def test_dialog_defaults_off_and_cancel_does_not_mutate(self):
        before = self.app.collection.to_dict()
        self.open_dialog()
        self.assertNotIn('selected', self.enabled.state())
        self.enabled.invoke()
        self.entry.set('East')
        self.cancel.invoke()
        self.assertEqual(self.app.collection.to_dict(), before)

    def test_dialog_saves_current_edit_and_preserves_edits_across_selection(self):
        self.open_dialog()
        self.enabled.invoke()
        self.entry.set('East')
        self.roster.selection_set('1')
        self.root.update()
        self.entry.set('West')
        data_file = Path(self.directory.name) / 'leagues.json'
        with patch('elo_calculator.DATA_FILE', data_file):
            self.save.invoke()
        restored = LeagueCollection.load(data_file).active.league
        self.assertTrue(restored.conferences_enabled)
        self.assertEqual([p.conference for p in restored.players], ['East', 'West', ''])
        self.assertEqual(self.app.audit_log.read()[-1]['action'], 'conferences_edited')
        self.assertTrue(list((Path(self.directory.name) / 'backups').glob('*.json')))
        self.app._show_error.assert_not_called()

    def test_failed_save_rolls_back_enabled_state_and_assignments(self):
        before = self.app.collection.to_dict()
        self.open_dialog()
        self.enabled.invoke()
        self.entry.set('East')
        with patch.object(LeagueCollection, 'save', side_effect=OSError('disk full')):
            self.save.invoke()
        self.assertEqual(self.app.collection.to_dict(), before)
        self.assertTrue(self.window.winfo_exists())
        self.app._show_error.assert_called_once()

    def test_filter_hidden_by_default_and_resets_on_disable_or_league_switch(self):
        self.app.conference_controls = Mock()
        self.app.conference_filter_combo = Mock()
        self.app.conference_filter_var = tk.StringVar(self.root, value='All players')
        self.assertIsNone(self.app._conference_player_ids())
        self.app.conference_controls.grid_remove.assert_called_once()
        self.app.league.configure_conferences(True, {0: 'East', 1: 'West', 2: ''})
        self.app._conference_player_ids()
        self.app.conference_filter_var.set('Conference: East')
        self.assertEqual(self.app._conference_player_ids(), {0})
        self.app.conference_filter_var.set('Unassigned players')
        self.assertEqual(self.app._conference_player_ids(), {2})
        self.app.league.conferences_enabled = False
        self.assertIsNone(self.app._conference_player_ids())
        self.assertEqual(self.app.conference_filter_var.get(), 'All players')
        self.app.league = League.new(2)
        self.assertIsNone(self.app._conference_player_ids())

    def test_complete_ui_keeps_default_view_and_filters_enabled_conferences(self):
        directory = Path(self.directory.name)
        with patch.multiple('elo_calculator', DATA_FILE=directory / 'data.json',
                            SETTINGS_FILE=directory / 'settings.json',
                            BACKUP_DIRECTORY=directory / 'backups',
                            AUDIT_LOG_FILE=directory / 'audit.jsonl',
                            RECOVERY_DIRECTORY=directory / 'recovery'), \
             patch.object(EloCalculatorApp, '_set_title_bar_theme'):
            app = EloCalculatorApp(self.root)
            self.root.update_idletasks()
            self.assertFalse(app.league.conferences_enabled)
            self.assertEqual(app.conference_controls.winfo_manager(), '')
            self.assertEqual(len(app.standings.get_children()), 12)
            self.root.update_idletasks()
            app.league.configure_conferences(True, {p.id: 'East' if p.id < 3 else 'West' for p in app.league.players})
            for theme in ('light', 'dark'):
                app.theme_var.set(theme)
                app._apply_theme(theme, save=False)
                app._refresh_standings()
                app.conference_filter_var.set('Conference: East')
                app._refresh_standings()
                self.assertEqual(app.conference_controls.winfo_manager(), 'grid')
                self.assertEqual(app.standings.get_children(), ('0', '1', '2'))
                self.assertEqual([int(app.standings.item(item, 'values')[0])
                                  for item in app.standings.get_children()], [1, 2, 3])
            app.league.conferences_enabled = False
            app._refresh_standings()
            self.assertEqual(app.conference_controls.winfo_manager(), '')
            self.assertEqual(len(app.standings.get_children()), 12)
            # Drain queued theme/title callbacks before destroying this Tcl root.
            self.root.update_idletasks()


if __name__ == '__main__':
    unittest.main()

# Purpose: Guard optional conference behavior, migration, ranks and transactional UI.
# Upstream: elo_model.py owns league data; elo_calculator.py renders/settings;
# elo_storage.py saves/backups/audits. Environment: Python 3.12 / Windows Tk 8.6.
# Generated: 2026-09-24 America/New_York. Changes: New conference regression suite.
