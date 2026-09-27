# test_elo_names.py
# Request: Prevent Unicode player names from crashing sorting and saved-app startup.
"""Natural ordering and real-UI rename/save/reopen regressions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import patch

from elo_calculator import EloCalculatorApp, _natural_sort_key
from elo_storage import LeagueCollection


class NaturalNameTests(unittest.TestCase):
    def test_non_decimal_digits_remain_text(self):
        for name in ('\u00b2', '\u2460', '\u00b2\u00b3', '1\u00b2'):
            with self.subTest(name=name):
                key = _natural_sort_key(name)
                self.assertIn(name if name != '1\u00b2' else '\u00b2', key)

    def test_decimal_digits_keep_natural_order(self):
        for two, ten in (('2', '10'), ('\u0662', '\u0661\u0660'),
                         ('\uff12', '\uff11\uff10')):
            with self.subTest(two=two, ten=ten):
                names = [f'Player {ten}', f'Player {two}']
                self.assertEqual(sorted(names, key=_natural_sort_key), names[::-1])


class TkPlayerNameTests(unittest.TestCase):
    def test_unicode_rename_saves_and_reopens(self):
        for name in ('\u00b2', '\u2460'):
            with self.subTest(name=name), TemporaryDirectory() as directory:
                folder = Path(directory)
                with patch.multiple(
                    'elo_calculator', DATA_FILE=folder / 'data.json',
                    SETTINGS_FILE=folder / 'settings.json',
                    BACKUP_DIRECTORY=folder / 'backups',
                    AUDIT_LOG_FILE=folder / 'audit.jsonl',
                    RECOVERY_DIRECTORY=folder / 'recovery',
                ), patch.object(EloCalculatorApp, '_set_title_bar_theme'):
                    for reopening in (False, True):
                        try:
                            root = tk.Tk()
                        except tk.TclError as error:
                            self.skipTest(f'Tk unavailable: {error}')
                        root.withdraw()
                        try:
                            app = EloCalculatorApp(root)
                            if not reopening:
                                app.standings.selection_set('0')
                                with patch.object(app, '_ask_text', return_value=name):
                                    app._rename_player()
                            self.assertEqual(app.league.player(0).name, name)
                            self.assertIn(name, app.winner_combo['values'])
                            self.assertEqual(app.standings.item('0', 'values')[1], name)
                            restored = LeagueCollection.load(folder / 'data.json')
                            self.assertEqual(restored.active.league.player(0).name, name)
                        finally:
                            root.update_idletasks()
                            root.destroy()


if __name__ == '__main__':
    unittest.main()

# Purpose: Cover Unicode name sorting and persisted startup after a GUI rename.
# Upstream: elo_calculator.py sorts UI names; elo_storage.py persists league data.
# Upstream purpose: Display editable standings and restore saved player identities.
# Environment: Python 3.12 / Windows Tk 8.6; temporary storage only.
# Generated: 2026-09-24 20:53 America/New_York. Changes: New regression test file.
