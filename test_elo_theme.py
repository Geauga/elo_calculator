# test_elo_theme.py
# Request: Verify light/dark compatibility and live theme switching regressions.
"""Real Tk style tests; skipped only when no working Tk display is available."""

import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock

from elo_calculator import EloCalculatorApp, THEME_PALETTES
from elo_model import League


def contrast(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                  for v in channels]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


class GraphThemeTests(unittest.TestCase):
    def test_h2h_records_use_high_contrast_text_inside_bars(self) -> None:
        for theme, colors in THEME_PALETTES.items():
            with self.subTest(theme=theme):
                app = object.__new__(EloCalculatorApp)
                app.theme_var = Mock(get=Mock(return_value=theme))
                app.league = League.new(2)
                app.league.record_match(0, 1, 0)
                app.graph_canvas = Mock()
                app.graph_canvas.winfo_width.return_value = 600
                app.graph_canvas.winfo_height.return_value = 300
                app.graph_player_combo = Mock(get=Mock(return_value="Player 1"))
                app.player_name_to_id = {"Player 1": 0}
                app.graph_metric_var = Mock(get=Mock(return_value="h2h"))
                app._refresh_graph()
                records = [call.kwargs for call in app.graph_canvas.create_text.call_args_list
                           if call.kwargs.get("text") == "1-0-0"]
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["fill"], colors["selection_text"])
                self.assertGreaterEqual(contrast(records[0]["fill"], colors["selection"]), 4.5)


class TkThemeTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display/library unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = object.__new__(EloCalculatorApp)
        self.app.root = self.root
        self.app.style = ttk.Style(self.root)
        self.app.style.theme_use("clam")
        self.app.theme_var = tk.StringVar(self.root, value="light")
        self.app._set_title_bar_theme = Mock()

    def apply(self, theme: str) -> dict[str, str]:
        self.app.theme_var.set(theme)
        self.app._apply_theme(theme, save=False)
        return THEME_PALETTES[theme]

    def test_notebook_and_combo_states_follow_both_palettes(self) -> None:
        for theme in ("light", "dark", "light"):
            colors = self.apply(theme)
            for state in ((), ("selected",), ("active",), ("selected", "active")):
                with self.subTest(theme=theme, state=state):
                    foreground = self.app.style.lookup("TNotebook.Tab", "foreground", state)
                    background = self.app.style.lookup("TNotebook.Tab", "background", state)
                    self.assertGreaterEqual(contrast(foreground, background), 4.5)
            for state in (("active", "readonly"), ("pressed", "readonly")):
                self.assertEqual(self.app.style.lookup("TCombobox", "background", state),
                                 colors["button_active"])
                self.assertEqual(self.app.style.lookup("TCombobox", "arrowcolor", state),
                                 colors["foreground"])

    def test_existing_and_new_popdowns_follow_repeated_theme_switches(self) -> None:
        self.apply("light")
        frame = ttk.Frame(self.root)
        combo = ttk.Combobox(frame, values=("One", "Two"), state="readonly")
        popup = str(self.root.tk.call("ttk::combobox::PopdownWindow", str(combo)))
        for theme in ("dark", "light", "dark"):
            colors = self.apply(theme)
            fresh = ttk.Combobox(frame, values=("Three",), state="readonly")
            fresh_popup = str(self.root.tk.call("ttk::combobox::PopdownWindow", str(fresh)))
            for path in (popup, fresh_popup):
                for option, key in (("background", "field"), ("foreground", "foreground"),
                                    ("selectbackground", "selection"),
                                    ("selectforeground", "selection_text")):
                    with self.subTest(theme=theme, option=option):
                        self.assertEqual(self.root.tk.call(path + ".f.l", "cget", "-" + option),
                                         colors[key])
            fresh.destroy()

    def test_selection_and_information_text_remain_readable(self) -> None:
        for theme in ("light", "dark"):
            colors = self.apply(theme)
            for style in ("TEntry", "TSpinbox"):
                for state in ((), ("focus",)):
                    self.assertEqual(self.app.style.lookup(style, "selectbackground", state),
                                     colors["selection"])
                    self.assertEqual(self.app.style.lookup(style, "selectforeground", state),
                                     colors["selection_text"])
            foreground = self.app.style.lookup("Information.TLabel", "foreground")
            background = self.app.style.lookup("Information.TLabel", "background")
            self.assertGreaterEqual(contrast(foreground, background), 4.5)

    def test_scrollbar_and_disabled_button_states_follow_palette(self) -> None:
        for theme in ("light", "dark"):
            colors = self.apply(theme)
            for style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
                self.assertEqual(self.app.style.lookup(style, "background"), colors["button_active"])
                self.assertEqual(self.app.style.lookup(style, "arrowcolor"), colors["foreground"])
                for state in (("active",), ("pressed",)):
                    self.assertEqual(self.app.style.lookup(style, "background", state), colors["border"])
            self.assertEqual(self.app.style.lookup("TButton", "foreground", ("disabled",)),
                             colors["disabled"])


if __name__ == "__main__":
    unittest.main()

# Purpose: Guard palette contrast, Tk state maps, cached popdowns, and graph labels.
# Upstream: elo_calculator.py and elo_model.py supply GUI styling and match data.
# Upstream purpose: Display and manage persistent Elo leagues.
# Environment: Python 3.10+ with Tk 8.6; live tests require a working GUI runtime.
# Generated: 2026-09-09 21:27 America/New_York.
# Changes: New file; all lines add theme compatibility regression coverage.
