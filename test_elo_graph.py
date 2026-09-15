# test_elo_graph.py
# Request: Fix extreme-Elo graph crashes, slow rank histories and crowded labels.
"""Numeric, ranking-equivalence and real-canvas graph regressions."""

from copy import deepcopy
from itertools import permutations
import math
import random
import sys
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from elo_calculator import (
    EloCalculatorApp, _graph_bounds, _graph_fraction,
    _player_rank_history, _ranked_players,
)
from elo_model import League


class GraphRangeTests(unittest.TestCase):
    def test_constant_ranges_remain_finite_and_nonzero(self):
        for value in (0.0, 1500.0, 1e20, -1e20, sys.float_info.max, -sys.float_info.max):
            with self.subTest(value=value):
                low, high = _graph_bounds([value, value])
                self.assertTrue(math.isfinite(low) and math.isfinite(high))
                self.assertLess(low, high)
                self.assertLessEqual(low, value)
                self.assertGreaterEqual(high, value)
                self.assertTrue(0 <= _graph_fraction(value, low, high) <= 1)

    def test_extreme_and_adjacent_ranges_normalize_without_overflow(self):
        for low, high in ((-sys.float_info.max, sys.float_info.max),
                          (1e20, math.nextafter(1e20, math.inf)),
                          (-1e20, math.nextafter(-1e20, math.inf)),
                          (0.0, math.ulp(0.0))):
            with self.subTest(low=low, high=high):
                self.assertEqual(_graph_fraction(low, low, high), 0.0)
                self.assertEqual(_graph_fraction(high, low, high), 1.0)


class RankHistoryTests(unittest.TestCase):
    @staticmethod
    def fixture(rated):
        league = League.new(5)
        league.allow_draws = True
        league.calculate_elo = rated
        league.base_elo = 1234.0
        for index, player in enumerate(league.players):
            player.id = 10 + index * 3
            player.rating = 1234.0
            player.name = ("Player 10", "Player 2", "Alpha", "Beta", "Unplayed")[index]
        rng = random.Random(417)
        for index in range(36):
            first, second = rng.sample([10, 13, 16, 19], 2)
            if index % 5 == 0:
                league.record_draw(first, second)
            else:
                league.record_match(first, second, index % league.win_condition.games_to_win)
        return league

    @staticmethod
    def slow_history(league):
        """Independent prefix replay using the original standings/statistics path."""
        sim = deepcopy(league)
        sim.matches = []
        for player in sim.players:
            for match in league.matches:
                if player.id == match.winner_id:
                    player.rating = match.winner_rating_before
                    break
                if player.id == match.loser_id:
                    player.rating = match.loser_rating_before
                    break
        ranks = {p.id: [] for p in sim.players}

        def collect():
            for position, player in enumerate(_ranked_players(sim), 1):
                ranks[player.id].append(position)

        collect()
        for match in league.matches:
            sim.player(match.winner_id).rating += match.rating_change
            sim.player(match.loser_id).rating -= match.rating_change
            sim.matches.append(match)
            collect()
        return ranks

    def test_incremental_ranks_match_prefix_replay_for_every_hierarchy(self):
        for rated in (False, True):
            league = self.fixture(rated)
            for hierarchy in permutations(league.tiebreaker_hierarchy):
                league.tiebreaker_hierarchy = list(hierarchy)
                before = league.to_dict()
                expected = self.slow_history(league)
                for player in league.players:
                    with self.subTest(rated=rated, hierarchy=hierarchy, player=player.id):
                        self.assertEqual(_player_rank_history(league, player.id), expected[player.id])
                self.assertEqual(league.to_dict(), before)

    def test_rank_replay_does_not_rescan_match_statistics(self):
        league = self.fixture(False)
        with patch.object(League, "statistics", side_effect=AssertionError("history rescan")), \
             patch.object(League, "head_to_head_percentages", side_effect=AssertionError("H2H rescan")), \
             patch.object(League, "head_to_head_game_percentages", side_effect=AssertionError("game rescan")):
            self.assertEqual(len(_player_rank_history(league, 10)), len(league.matches) + 1)


class TkGraphTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display/library unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = object.__new__(EloCalculatorApp)
        self.app.league = League.new(2)
        self.canvas = self.app.graph_canvas = tk.Canvas(self.root, width=600, height=300)
        self.canvas.winfo_width = Mock(return_value=600)
        self.canvas.winfo_height = Mock(return_value=300)
        self.app.graph_player_combo = Mock(get=Mock(return_value="Player 1"))
        self.app.player_name_to_id = {"Player 1": 0}
        self.app.graph_metric_var = tk.StringVar(self.root, value="elo")
        self.app.theme_var = tk.StringVar(self.root, value="light")

    def test_extreme_elo_graphs_have_finite_coordinates(self):
        for base in (1e20, -1e20, sys.float_info.max, -sys.float_info.max):
            self.app.league.base_elo = base
            for player in self.app.league.players:
                player.rating = base
            self.app.league.matches = []
            for count in (0, 1):
                if count:
                    self.app.league.record_match(0, 1, 0)
                with self.subTest(base=base, matches=count):
                    self.app._refresh_graph()
                    self.assertEqual(len(self.app._graph_point_labels), count + 1)
                    for item in self.canvas.find_all():
                        self.assertTrue(all(math.isfinite(v) for v in self.canvas.coords(item)))
                        if self.canvas.type(item) == "text":
                            self.assertNotIn("inf", self.canvas.itemcget(item, "text"))

    def test_sparse_graph_keeps_all_result_labels_including_the_baseline(self):
        self.app.league.record_match(0, 1, 0)
        self.app.league.record_match(1, 0, 0)
        self.app._refresh_graph()
        self.assertEqual(len(self.canvas.find_withtag("graph-value")), 3)
        self.assertEqual(len(self.app._graph_point_labels), 3)

    def assert_labels_separated(self):
        labels = self.canvas.find_withtag("graph-value")
        self.assertGreater(len(labels), 0)
        self.assertLess(len(labels), 31)
        for index, label in enumerate(labels):
            left, top, right, bottom = self.canvas.bbox(label)
            self.assertGreaterEqual(left, 45)
            self.assertLessEqual(right, self.canvas.winfo_width())
            for other in labels[index + 1:]:
                x1, y1, x2, y2 = self.canvas.bbox(other)
                self.assertTrue(right <= x1 or x2 <= left or bottom <= y1 or y2 <= top)

    def test_dense_labels_remain_readable_and_every_point_has_a_hover_value(self):
        self.app.league.calculate_elo = False
        for _ in range(30):
            self.app.league.record_match(0, 1, 0)
        for theme, width in (("light", 600), ("dark", 300), ("light", 900)):
            self.app.theme_var.set(theme)
            self.canvas.winfo_width.return_value = width
            self.app._refresh_graph()
            self.assert_labels_separated()
            self.assertEqual(len(self.app._graph_point_labels), 31)
            for marker, (_, _, value, _) in self.app._graph_point_labels.items():
                with patch.object(self.canvas, "find_withtag", return_value=(marker,)):
                    self.app._show_graph_hover()
                tooltip = self.canvas.find_withtag("graph-hover")
                texts = [item for item in tooltip if self.canvas.type(item) == "text"]
                self.assertEqual([self.canvas.itemcget(item, "text") for item in texts], [value])
                self.assertEqual(self.canvas.itemcget(texts[0], "fill"), self.app._graph_colors()["text"])
                left, top, right, bottom = self.canvas.bbox("graph-hover")
                self.assertTrue(0 <= left < right <= width)
                self.assertTrue(0 <= top < bottom <= 300)
            self.app._hide_graph_hover()
            self.assertEqual(self.canvas.find_withtag("graph-hover"), ())

    def test_repeated_redraw_releases_old_click_callbacks(self):
        for _ in range(10):
            self.app.league.record_match(0, 1, 0)
        self.app._refresh_graph()
        initial_commands = len(self.canvas._tclCommands or [])
        self.assertEqual(initial_commands, 10)
        for metric in ("rank", "match_pct", "game_pct", "sb", "elo"):
            self.app.graph_metric_var.set(metric)
            self.app._refresh_graph()
            self.assertEqual(len(self.canvas._tclCommands or []), initial_commands)
            self.assertEqual(len(self.app._graph_point_bindings), 10)
            for marker, binding in self.app._graph_point_bindings:
                self.assertIn(binding, self.canvas.tag_bind(marker, "<Button-1>"))


if __name__ == "__main__":
    unittest.main()

# Purpose: Prevent numerical, ranking and real-Tk graph regressions.
# Upstream: elo_model.py owns match data; elo_calculator.py renders/ranks it.
# Environment: Python 3.12 / Windows Tk 8.6; generated 2026-09-14 America/New_York.
# Changes: New file; range, replay-equivalence, labels/hover and callback tests.
