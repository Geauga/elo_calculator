# test_elo_model.py
# Request: Add regressions for reviewed settings, replay, recovery, and UI defects.
"""Tests for the Elo league rules."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from elo_calculator import (
    ApplicationInstanceLock,
    EloCalculatorApp,
    STANDINGS_COLUMN_IDS,
    THEME_PALETTES,
    _player_elo_history,
    fit_window_to_screen,
    load_app_settings,
    load_theme,
    load_visible_columns,
    preserve_unreadable_database,
    save_theme,
)
from elo_model import (
    DEFAULT_TIEBREAKER_HIERARCHY,
    DEFAULT_ELO_DECIMAL_PLACES,
    INITIAL_RATING,
    K_FACTOR,
    LEAGUE_SCHEMA_VERSION,
    MAX_CUSTOM_SCORE,
    MAX_ELO_DECIMAL_PLACES,
    MAX_K_FACTOR,
    MAX_PLAYER_COUNT,
    MIN_K_FACTOR,
    MIN_PLAYER_COUNT,
    SCORE_MODE_CUSTOM,
    SCORE_MODE_FIXED,
    League,
    WinCondition,
    expected_score,
    rating_change,
)
from elo_simulator import (
    MAX_SIMULATIONS,
    simulate_first_to_n_league,
    simulate_first_to_n_season,
    simulation_limit,
)
from elo_storage import AuditLog, BackupManager, LeagueCollection


class EloModelTests(unittest.TestCase):
    def test_equal_players_have_even_expectation(self) -> None:
        self.assertAlmostEqual(expected_score(1500.0, 1500.0), 0.5)

    def test_expected_score_rejects_nonfinite_and_non_numeric_ratings(self) -> None:
        invalid_ratings = (
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            "1500",
        )
        for invalid_rating in invalid_ratings:
            with self.subTest(invalid_rating=invalid_rating):
                with self.assertRaisesRegex(ValueError, "Ratings must be finite"):
                    expected_score(invalid_rating, 1500.0)
                with self.assertRaisesRegex(ValueError, "Ratings must be finite"):
                    expected_score(1500.0, invalid_rating)

    def test_score_margins_scale_equal_rating_change(self) -> None:
        self.assertAlmostEqual(rating_change(1500.0, 1500.0, 0.50), 8.0)
        self.assertAlmostEqual(rating_change(1500.0, 1500.0, 0.75), 12.0)
        self.assertAlmostEqual(rating_change(1500.0, 1500.0, 1.0), 16.0)

    def test_first_to_n_simulator_is_seeded_and_read_only(self) -> None:
        league = League.new(4)
        for player, rating in zip(
            league.players, (2000.0, 1600.0, 1400.0, 1000.0)
        ):
            player.rating = rating
        original = league.to_dict()

        first = simulate_first_to_n_league(league, 500, seed=6166)
        second = simulate_first_to_n_league(league, 500, seed=6166)

        self.assertEqual(first, second)
        self.assertEqual(league.to_dict(), original)
        self.assertEqual(first.games_to_win, 3)
        self.assertEqual(first.matches_per_simulation, 6)
        self.assertAlmostEqual(
            sum(player.title_probability for player in first.players), 100.0
        )
        self.assertAlmostEqual(
            sum(player.average_matches_won for player in first.players), 6.0
        )
        for player in first.players:
            self.assertAlmostEqual(
                player.average_matches_won + player.average_matches_lost,
                3.0,
            )
        by_id = {player.player_id: player for player in first.players}
        self.assertGreater(
            by_id[0].title_probability, by_id[3].title_probability
        )

    def test_first_to_n_simulator_validates_format_and_workload(self) -> None:
        league = League.new(2)
        self.assertEqual(simulation_limit(2), MAX_SIMULATIONS)
        self.assertLess(simulation_limit(64, 100), 100)
        for simulations in (0, MAX_SIMULATIONS + 1, True):
            with self.subTest(simulations=simulations):
                with self.assertRaises(ValueError):
                    simulate_first_to_n_league(league, simulations)

        league.win_condition = WinCondition(score_mode=SCORE_MODE_CUSTOM)
        with self.assertRaises(ValueError):
            simulate_first_to_n_league(league, 10)

    def test_concrete_simulated_season_is_seeded_and_read_only(self) -> None:
        league = League.new(4)
        original = league.to_dict()

        first = simulate_first_to_n_season(league, seed=6166)
        second = simulate_first_to_n_season(league, seed=6166)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 6)
        self.assertEqual(
            {frozenset((match.winner_id, match.loser_id)) for match in first},
            {
                frozenset((left, right))
                for left in range(4)
                for right in range(left + 1, 4)
            },
        )
        self.assertTrue(
            all(
                match.winner_games == league.win_condition.games_to_win
                and 0 <= match.loser_games < match.winner_games
                for match in first
            )
        )
        self.assertEqual(league.to_dict(), original)

    def test_concrete_simulated_season_can_update_a_league(self) -> None:
        league = League.new(4)
        simulated_matches = simulate_first_to_n_season(league, seed=42)

        for simulated in simulated_matches:
            league.record_match(
                simulated.winner_id,
                simulated.loser_id,
                simulated.loser_games,
                simulated.winner_games,
            )

        self.assertEqual(len(league.matches), 6)
        self.assertEqual(
            [
                (match.winner_id, match.loser_id, match.winner_games, match.loser_games)
                for match in league.matches
            ],
            [
                (match.winner_id, match.loser_id, match.winner_games, match.loser_games)
                for match in simulated_matches
            ],
        )
        self.assertTrue(
            any(player.rating != INITIAL_RATING for player in league.players)
        )

    def test_graph_colors_follow_light_and_dark_theme_palettes(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.theme_var = Mock()

        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                app.theme_var.get.return_value = theme
                graph_colors = app._graph_colors()
                palette = THEME_PALETTES[theme]
                self.assertEqual(graph_colors["background"], palette["field"])
                self.assertEqual(graph_colors["axis"], palette["border"])
                self.assertEqual(graph_colors["grid"], palette["button_active"])
                self.assertEqual(graph_colors["text"], palette["muted"])
                self.assertEqual(graph_colors["plot"], palette["selection"])

    def test_elo_history_uses_the_saved_starting_rating(self) -> None:
        league = League.new(3)
        league.base_elo = 1200.0
        league.reset_standings()
        match = league.record_match(0, 1, 0)

        self.assertEqual(
            _player_elo_history(league, 0),
            [1200.0, 1200.0 + match.rating_change],
        )
        self.assertEqual(_player_elo_history(league, 2), [1200.0])

    def test_dynamic_settings_window_size_is_capped_to_usable_screen(self) -> None:
        self.assertEqual(fit_window_to_screen(1920, 1080, 560, 760), (560, 760))
        self.assertEqual(fit_window_to_screen(1920, 1080, 620, 1400), (620, 980))
        self.assertEqual(fit_window_to_screen(800, 600, 560, 760), (560, 500))
        self.assertEqual(fit_window_to_screen(400, 300, 560, 760), (320, 200))

    def test_league_heading_and_window_title_use_ascii_safe_separators(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        app.league_name_to_id = {}
        app.league_combo = {}
        app.league_var = Mock()
        app.heading_var = Mock()
        app.root = Mock()

        app._refresh_league_selector()

        app.heading_var.set.assert_called_once_with(
            "12-Player Elo League - First to 3"
        )
        app.root.title.assert_called_once_with(
            "League 1 - 12-Player Elo League - First to 3"
        )

    def test_fully_tied_standings_use_natural_player_name_order(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(12)
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()

        app._refresh_standings()

        displayed_names = [
            call.kwargs["values"][1]
            for call in app.standings.insert.call_args_list
        ]
        self.assertEqual(
            displayed_names,
            [f"Player {number}" for number in range(1, 13)],
        )

    def test_standings_menu_label_follows_the_draw_setting(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(2)
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()
        app.settings_menu = Mock()
        app.column_menu_indices = {"match_record": 7}

        app._refresh_standings()
        app.settings_menu.entryconfigure.assert_called_with(
            7,
            label="Show Match W-D-L",
        )

        app.league.allow_draws = False
        app.settings_menu.reset_mock()
        app._refresh_standings()
        app.settings_menu.entryconfigure.assert_called_with(
            7,
            label="Show Match W-L",
        )

    def test_head_to_head_is_the_secondary_standings_tiebreaker(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(3)
        app.league.calculate_elo = False
        app.league.players[2].rating = 1400.0
        app.league.record_match(0, 1, 0)
        for _ in range(3):
            app.league.record_match(2, 0, 0)
        for _ in range(2):
            app.league.record_match(1, 2, 0)
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()

        statistics = app.league.statistics()
        self.assertLess(
            statistics[0].match_win_percentage,
            statistics[1].match_win_percentage,
        )
        app._refresh_standings()

        displayed_names = [
            call.kwargs["values"][1]
            for call in app.standings.insert.call_args_list
        ]
        self.assertEqual(displayed_names[:2], ["Player 1", "Player 2"])

    def test_display_tied_elo_uses_head_to_head_despite_float_residue(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(2)
        app.league.calculate_elo = False
        app.league.elo_decimal_places = 2
        app.league.players[0].rating = 1503.0399999999997
        app.league.players[1].rating = 1503.0400000000002
        app.league.record_match(0, 1, 0)
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()

        self.assertEqual(
            app._format_elo(app.league.players[0].rating),
            app._format_elo(app.league.players[1].rating),
        )
        app._refresh_standings()

        displayed_names = [
            call.kwargs["values"][1]
            for call in app.standings.insert.call_args_list
        ]
        self.assertEqual(displayed_names, ["Player 1", "Player 2"])

    def test_head_to_head_game_percentage_is_the_third_tiebreaker(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(3)
        app.league.calculate_elo = False
        app.league.record_match(0, 1, 0)
        app.league.record_match(1, 2, 2)
        app.league.record_match(2, 0, 2)
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()

        head_to_head_games = app.league.head_to_head_game_percentages(
            {0, 1, 2}
        )
        self.assertGreater(head_to_head_games[0], head_to_head_games[2])
        self.assertGreater(head_to_head_games[2], head_to_head_games[1])
        app._refresh_standings()

        displayed_names = [
            call.kwargs["values"][1]
            for call in app.standings.insert.call_args_list
        ]
        self.assertEqual(displayed_names, ["Player 1", "Player 3", "Player 2"])

    def test_standings_apply_every_documented_tiebreaker(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(4)
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()
        statistics = {}
        for player in app.league.players:
            statistics[player.id] = Mock(
                matches_won=0,
                matches_drawn=0,
                matches_lost=0,
                games_won=0,
                games_lost=0,
                match_win_percentage=0.0,
                sb_score=0.0,
                game_win_percentage=0.0,
            )
        statistics[0].match_win_percentage = 25.0
        statistics[0].sb_score = 10.0
        statistics[0].game_win_percentage = 100.0
        statistics[1].match_win_percentage = 50.0
        statistics[2].match_win_percentage = 50.0
        statistics[2].sb_score = 2.0
        statistics[3].match_win_percentage = 50.0
        statistics[3].sb_score = 2.0
        statistics[3].game_win_percentage = 80.0
        app.league.statistics = Mock(return_value=statistics)

        app._refresh_standings()

        displayed_names = [
            call.kwargs["values"][1]
            for call in app.standings.insert.call_args_list
        ]
        self.assertEqual(
            displayed_names,
            ["Player 4", "Player 3", "Player 2", "Player 1"],
        )

    def test_sb_graph_updates_when_an_opponent_plays(self) -> None:
        league = League.new(3)
        league.record_match(0, 1, 0)
        league.record_match(1, 2, 0)
        self.assertEqual(league.statistics()[0].sb_score, 1.0)

        app = object.__new__(EloCalculatorApp)
        app.league = league
        app.graph_canvas = Mock()
        app.graph_canvas.winfo_width.return_value = 400
        app.graph_canvas.winfo_height.return_value = 300
        app.graph_player_combo = Mock(get=Mock(return_value="Player 1"))
        app.player_name_to_id = {"Player 1": 0}
        app.graph_metric_var = Mock(get=Mock(return_value="sb"))
        app.theme_var = Mock(get=Mock(return_value="light"))

        app._refresh_graph()

        graph_lines = [
            call
            for call in app.graph_canvas.create_line.call_args_list
            if call.kwargs.get("width") == 2
        ]
        self.assertEqual(len(graph_lines), 1)
        points = graph_lines[0].args[0]
        self.assertEqual(len(points), 6)
        self.assertLess(points[-1], points[-3])

    def test_first_to_n_simulator_shares_fully_tied_title_and_rank(self) -> None:
        league = League.new(3)
        league.calculate_elo = False
        league.win_condition = WinCondition(
            games_to_win=1,
            score_multipliers={0: 1.0},
            score_mode=SCORE_MODE_FIXED,
        )

        result = simulate_first_to_n_league(league, simulations=1, seed=2)

        for player in result.players:
            self.assertAlmostEqual(player.title_probability, 100.0 / 3.0)
            self.assertEqual(player.average_rank, 2.0)
            self.assertEqual(player.average_matches_won, 1.0)
            self.assertEqual(player.average_matches_lost, 1.0)

    def test_simulator_uses_head_to_head_after_match_wins(self) -> None:
        league = League.new(7)
        league.calculate_elo = False
        league.win_condition = WinCondition(
            games_to_win=1,
            score_multipliers={0: 1.0},
            score_mode=SCORE_MODE_FIXED,
        )

        result = simulate_first_to_n_league(league, simulations=1, seed=4)
        by_id = {player.player_id: player for player in result.players}

        self.assertEqual(by_id[2].average_matches_won, 4.0)
        self.assertEqual(by_id[4].average_matches_won, 4.0)
        self.assertEqual(by_id[2].title_probability, 100.0)
        self.assertEqual(by_id[4].title_probability, 0.0)
        self.assertEqual(by_id[2].average_rank, 1.0)
        self.assertEqual(by_id[4].average_rank, 2.0)

    def test_simulator_uses_head_to_head_games_as_third_tiebreaker(self) -> None:
        league = League.new(4)
        league.calculate_elo = False

        result = simulate_first_to_n_league(league, simulations=1, seed=8)
        by_id = {player.player_id: player for player in result.players}

        for player_id in (0, 1, 2):
            self.assertEqual(by_id[player_id].average_matches_won, 2.0)
        self.assertEqual(by_id[1].title_probability, 100.0)
        self.assertEqual(by_id[1].average_rank, 1.0)
        self.assertEqual(by_id[0].average_rank, 2.0)
        self.assertEqual(by_id[2].average_rank, 3.0)

    def test_custom_k_factor_and_rounding_control_transfer(self) -> None:
        self.assertEqual(
            rating_change(
                1500.0, 1500.0, k_factor=20.0, decimal_places=0
            ),
            10.0,
        )
        full_precision = rating_change(
            1432.25, 1617.75, 0.75, k_factor=40.0
        )
        rounded = rating_change(
            1432.25,
            1617.75,
            0.75,
            k_factor=40.0,
            decimal_places=1,
        )
        self.assertEqual(rounded, round(full_precision, 1))

    def test_invalid_elo_settings_are_rejected(self) -> None:
        for k_factor in (
            0,
            -1,
            MIN_K_FACTOR / 2,
            MAX_K_FACTOR + 1,
            float("nan"),
            float("inf"),
            True,
        ):
            with self.subTest(k_factor=k_factor):
                with self.assertRaises(ValueError):
                    rating_change(1500.0, 1500.0, k_factor=k_factor)

        for decimal_places in (-1, MAX_ELO_DECIMAL_PLACES + 1, True):
            with self.subTest(decimal_places=decimal_places):
                with self.assertRaises(ValueError):
                    rating_change(
                        1500.0,
                        1500.0,
                        decimal_places=decimal_places,
                    )

    def test_configurable_league_settings_round_trip_and_validate(self) -> None:
        league = League.new(2)
        league.base_elo = 1200.0
        league.k_factor_scaling = True
        league.tiebreaker_hierarchy = list(
            reversed(DEFAULT_TIEBREAKER_HIERARCHY)
        )

        restored = League.from_dict(league.to_dict())

        self.assertEqual(restored.base_elo, 1200.0)
        self.assertTrue(restored.k_factor_scaling)
        self.assertEqual(
            restored.tiebreaker_hierarchy,
            list(reversed(DEFAULT_TIEBREAKER_HIERARCHY)),
        )
        self.assertEqual(restored.to_dict()["schema_version"], LEAGUE_SCHEMA_VERSION)

        for invalid_base in (float("nan"), float("inf"), True, "1500", None):
            with self.subTest(invalid_base=invalid_base):
                data = League.new(2).to_dict()
                data["base_elo"] = invalid_base
                with self.assertRaisesRegex(ValueError, "invalid league settings"):
                    League.from_dict(data)

        for invalid_scaling in ("false", 0, 1, None):
            with self.subTest(invalid_scaling=invalid_scaling):
                data = League.new(2).to_dict()
                data["k_factor_scaling"] = invalid_scaling
                with self.assertRaisesRegex(ValueError, "invalid league settings"):
                    League.from_dict(data)

        invalid_hierarchies = (
            [],
            ["rating"] * len(DEFAULT_TIEBREAKER_HIERARCHY),
            [*DEFAULT_TIEBREAKER_HIERARCHY[:-1], "unknown"],
            "rating",
        )
        for invalid_hierarchy in invalid_hierarchies:
            with self.subTest(invalid_hierarchy=invalid_hierarchy):
                data = League.new(2).to_dict()
                data["tiebreaker_hierarchy"] = invalid_hierarchy
                with self.assertRaisesRegex(ValueError, "invalid league settings"):
                    League.from_dict(data)

    def test_schema_seven_defaults_new_settings_and_upgrades_to_eight(self) -> None:
        data = League.new(2).to_dict()
        data["schema_version"] = 7
        data.pop("base_elo")
        data.pop("k_factor_scaling")
        data.pop("tiebreaker_hierarchy")

        restored = League.from_dict(data)

        self.assertEqual(restored.base_elo, INITIAL_RATING)
        self.assertFalse(restored.k_factor_scaling)
        self.assertEqual(
            restored.tiebreaker_hierarchy,
            list(DEFAULT_TIEBREAKER_HIERARCHY),
        )
        self.assertEqual(restored.to_dict()["schema_version"], 8)

    def test_base_elo_is_used_when_roster_is_replayed(self) -> None:
        league = League.new(3)
        league.base_elo = 1200.0
        league.reset_standings()
        retained = league.record_match(0, 1, 0)
        expected_ratings = (league.player(0).rating, league.player(1).rating)

        league.resize_players(2)

        self.assertEqual(
            (league.player(0).rating, league.player(1).rating),
            expected_ratings,
        )
        self.assertEqual(league.matches[0].rating_change, retained.rating_change)
        self.assertEqual(league.matches[0].winner_rating_before, 1200.0)
        self.assertEqual(league.matches[0].loser_rating_before, 1200.0)

        established = League.new(3)
        established.record_match(0, 1, 0)
        original_ratings = (
            established.player(0).rating,
            established.player(1).rating,
        )
        established.base_elo = 1200.0
        established.resize_players(2)
        self.assertEqual(
            (established.player(0).rating, established.player(1).rating),
            original_ratings,
        )

    def test_k_factor_scaling_is_persisted_and_replayed(self) -> None:
        league = League.new(3)
        league.k_factor = MAX_K_FACTOR
        league.k_factor_scaling = True

        retained = league.record_match(0, 1, 0)
        expected_ratings = (league.player(0).rating, league.player(1).rating)
        restored = League.from_dict(league.to_dict())
        restored.resize_players(2)

        self.assertEqual(retained.rating_change, 650.0)
        self.assertEqual(retained.k_factor, MAX_K_FACTOR)
        self.assertEqual(retained.multiplier, 1.3)
        self.assertEqual(restored.matches[0].rating_change, 650.0)
        self.assertEqual(
            (restored.player(0).rating, restored.player(1).rating),
            expected_ratings,
        )

    def test_k_factor_scaling_validates_scores_before_scaling(self) -> None:
        league = League.new(2)
        league.k_factor_scaling = True
        state = league.to_dict()

        for winner_games, loser_games in (
            ("3", 0),
            (3, "0"),
            (3, True),
            (3, 0.5),
        ):
            with self.subTest(
                winner_games=winner_games,
                loser_games=loser_games,
            ):
                with self.assertRaises(ValueError):
                    league.record_match(
                        0,
                        1,
                        loser_games,
                        winner_games=winner_games,
                    )
                self.assertEqual(league.to_dict(), state)

    def test_simulators_apply_k_factor_scaling(self) -> None:
        league = League.new(2)
        league.k_factor_scaling = True

        with patch("elo_simulator.rating_change", wraps=rating_change) as change:
            season = simulate_first_to_n_season(league, seed=17)
        self.assertEqual(change.call_count, 1)
        expected_multiplier = league.elo_multiplier(
            season[0].loser_games,
            season[0].winner_games,
        )
        self.assertEqual(
            change.call_args.args[2],
            expected_multiplier,
        )

        with patch("elo_simulator.rating_change", wraps=rating_change) as change:
            simulate_first_to_n_league(league, simulations=1, seed=17)
        self.assertEqual(change.call_count, 1)
        self.assertEqual(change.call_args.args[2], expected_multiplier)

    def test_rating_overflow_is_rejected_without_mutating_league(self) -> None:
        with self.assertRaisesRegex(ValueError, "Rating change must be finite"):
            rating_change(1500.0, 1500.0, 1e308)

        league = League.new(2)
        league.win_condition = WinCondition(
            games_to_win=1,
            score_multipliers={0: 1e308},
        )
        ratings_before = [player.rating for player in league.players]

        with self.assertRaisesRegex(ValueError, "Rating change must be finite"):
            league.record_match(0, 1, 0)

        self.assertEqual([player.rating for player in league.players], ratings_before)
        self.assertEqual(league.matches, [])

    def test_match_is_zero_sum_and_keeps_decimal_precision(self) -> None:
        league = League.new()
        league.player(0).rating = 1432.25
        league.player(1).rating = 1617.75
        total_before = sum(player.rating for player in league.players)

        match = league.record_match(0, 1, 1)

        self.assertGreater(match.rating_change, 12.0)
        self.assertAlmostEqual(
            sum(player.rating for player in league.players), total_before
        )
        self.assertNotEqual(league.player(0).rating, round(league.player(0).rating))

    def test_match_and_individual_game_statistics(self) -> None:
        league = League.new(3)
        league.record_match(0, 1, 2)
        league.record_match(2, 0, 1)

        stats = league.statistics()

        self.assertEqual((stats[0].matches_won, stats[0].matches_lost), (1, 1))
        self.assertEqual((stats[0].games_won, stats[0].games_lost), (4, 5))
        self.assertAlmostEqual(stats[0].match_win_percentage, 50.0)
        self.assertAlmostEqual(stats[0].game_win_percentage, 100.0 * 4 / 9)
        self.assertEqual((stats[1].games_won, stats[1].games_lost), (2, 3))
        self.assertAlmostEqual(stats[1].game_win_percentage, 40.0)
        self.assertEqual((stats[2].games_won, stats[2].games_lost), (3, 1))
        self.assertAlmostEqual(stats[2].game_win_percentage, 75.0)

    def test_sonneborn_berger_uses_opponents_final_match_wins(self) -> None:
        league = League.new(4)
        league.record_match(0, 1, 0)
        league.record_match(0, 2, 0)
        league.record_match(1, 3, 0)
        league.record_match(1, 3, 0)
        league.record_match(2, 3, 0)

        stats = league.statistics()

        self.assertEqual(stats[0].sb_score, 3.0)
        self.assertEqual(stats[1].sb_score, 0.0)
        self.assertEqual(stats[2].sb_score, 0.0)

    def test_statistics_follow_undo_and_reset(self) -> None:
        league = League.new(3)
        league.record_match(0, 1, 0)
        league.record_match(1, 2, 1)
        league.undo_last_match()

        stats = league.statistics()
        self.assertEqual((stats[0].matches_won, stats[0].games_won), (1, 3))
        self.assertEqual((stats[2].matches_lost, stats[2].games_lost), (0, 0))

        league.reset_standings()
        self.assertTrue(
            all(
                item.matches_won == item.matches_lost
                == item.games_won == item.games_lost == 0
                for item in league.statistics().values()
            )
        )

    def test_undo_restores_exact_ratings(self) -> None:
        league = League.new()
        league.record_match(0, 1, 2)
        league.record_match(1, 0, 0)

        league.undo_last_match()

        self.assertAlmostEqual(league.player(0).rating, 1508.0)
        self.assertAlmostEqual(league.player(1).rating, 1492.0)
        self.assertEqual(len(league.matches), 1)

    def test_draw_between_equal_players_keeps_ratings_and_updates_statistics(self) -> None:
        league = League.new(2)

        match = league.record_draw(0, 1)
        stats = league.statistics()

        self.assertTrue(match.is_draw)
        self.assertEqual(match.rating_change, 0.0)
        self.assertEqual(league.player(0).rating, INITIAL_RATING)
        self.assertEqual(league.player(1).rating, INITIAL_RATING)
        self.assertEqual(stats[0].matches_drawn, 1)
        self.assertEqual(stats[1].matches_drawn, 1)
        self.assertEqual(stats[0].match_win_percentage, 50.0)
        self.assertEqual((stats[0].games_won, stats[0].games_lost), (0, 0))

    def test_draws_can_be_disabled_without_changing_existing_results(self) -> None:
        league = League.new(2)
        league.record_draw(0, 1)
        league.allow_draws = False

        with self.assertRaisesRegex(ValueError, "Draws are disabled"):
            league.record_draw(0, 1)

        self.assertEqual(len(league.matches), 1)
        self.assertTrue(league.matches[0].is_draw)
        self.assertEqual(league.statistics()[0].matches_drawn, 1)

    def test_allow_draws_setting_persists_and_older_saves_default_to_enabled(self) -> None:
        league = League.new(2)
        league.allow_draws = False

        restored = League.from_dict(league.to_dict())
        self.assertFalse(restored.allow_draws)

        legacy_data = league.to_dict()
        legacy_data["schema_version"] = 6
        legacy_data.pop("allow_draws")
        legacy = League.from_dict(legacy_data)
        self.assertTrue(legacy.allow_draws)

    def test_allow_draws_setting_must_be_boolean(self) -> None:
        data = League.new(2).to_dict()
        data["allow_draws"] = "yes"

        with self.assertRaisesRegex(ValueError, "allow-draws"):
            League.from_dict(data)

    def test_disabled_draws_disable_only_the_draw_ui_action(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(2)
        app.league.allow_draws = False
        app.player_name_to_id = {"Player 1": 0, "Player 2": 1}
        app.winner_var = Mock(get=Mock(return_value="Player 1"))
        app.loser_var = Mock(get=Mock(return_value="Player 2"))
        app.winner_games_var = Mock(get=Mock(return_value="3"))
        app.loser_games_var = Mock(get=Mock(return_value="0"))
        app.preview_var = Mock()
        app.record_button = Mock()
        app.draw_button = Mock()

        app._update_preview()

        app.record_button.configure.assert_called_with(state="normal")
        app.draw_button.configure.assert_called_with(state="disabled")
        self.assertIn(
            "Draws are disabled for this league.",
            app.preview_var.set.call_args.args[0],
        )

    def test_standings_hide_draw_column_when_draws_are_disabled(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.league = League.new(2)
        app.league.record_draw(0, 1)
        app.league.allow_draws = False
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()

        app._refresh_standings()

        app.standings.heading.assert_called_once_with(
            "match_record", text="Match W-L"
        )
        self.assertEqual(
            app.standings.insert.call_args_list[0].kwargs["values"][4], "0-0"
        )

        app.league.allow_draws = True
        app.standings.reset_mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()
        app._refresh_standings()

        app.standings.heading.assert_called_once_with(
            "match_record", text="Match W-D-L"
        )
        self.assertEqual(
            app.standings.insert.call_args_list[0].kwargs["values"][4], "0-1-0"
        )

    def test_draw_moves_unequal_ratings_toward_each_other_and_is_zero_sum(self) -> None:
        league = League.new(2)
        league.player(0).rating = 1700.0
        league.player(1).rating = 1500.0

        match = league.record_draw(0, 1)

        self.assertLess(match.rating_change, 0.0)
        self.assertLess(league.player(0).rating, 1700.0)
        self.assertGreater(league.player(1).rating, 1500.0)
        self.assertAlmostEqual(
            league.player(0).rating + league.player(1).rating, 3200.0
        )

    def test_draw_uses_and_persists_custom_k_factor_and_rounding(self) -> None:
        league = League.new(2)
        league.k_factor = 40.0
        league.elo_decimal_places = 1
        league.player(0).rating = 1700.0
        league.player(1).rating = 1500.0

        match = league.record_draw(0, 1)

        self.assertEqual(match.rating_change, -10.4)
        self.assertEqual(match.k_factor, 40.0)
        self.assertEqual(match.elo_decimal_places, 1)
        restored = League.from_dict(league.to_dict())
        self.assertEqual(restored.matches[0].rating_change, -10.4)
        self.assertEqual(restored.matches[0].k_factor, 40.0)

    def test_draw_persists_and_undo_restores_exact_ratings(self) -> None:
        league = League.new(2)
        league.player(0).rating = 1600.0
        league.player(1).rating = 1400.0
        before = (league.player(0).rating, league.player(1).rating)
        league.record_draw(0, 1)

        restored = League.from_dict(league.to_dict())
        self.assertTrue(restored.matches[0].is_draw)
        restored.undo_last_match()

        self.assertEqual(
            (restored.player(0).rating, restored.player(1).rating), before
        )

    def test_schema_five_match_defaults_to_non_draw(self) -> None:
        league = League.new(2)
        league.record_match(0, 1, 0)
        data = league.to_dict()
        data["schema_version"] = 5
        data["matches"][0].pop("is_draw")

        restored = League.from_dict(data)

        self.assertFalse(restored.matches[0].is_draw)

    def test_draw_contributes_half_opponent_match_score_to_sb(self) -> None:
        league = League.new(3)
        league.record_draw(0, 1)
        league.record_match(1, 2, 0)

        stats = league.statistics()

        self.assertEqual(stats[0].sb_score, 0.75)
        self.assertEqual(stats[1].sb_score, 0.25)

    def test_draw_is_replayed_when_roster_is_reduced(self) -> None:
        league = League.new(3)
        league.record_match(0, 1, 0)
        league.record_draw(0, 1)
        expected_ratings = (league.player(0).rating, league.player(1).rating)

        league.resize_players(2)

        self.assertTrue(league.matches[1].is_draw)
        self.assertAlmostEqual(league.player(0).rating, expected_ratings[0])
        self.assertAlmostEqual(league.player(1).rating, expected_ratings[1])

    def test_reset_restores_ratings_and_records_but_keeps_names(self) -> None:
        league = League.new()
        league.rename_player(0, "Alice")
        league.record_match(0, 1, 0)
        league.record_match(2, 3, 2)

        league.reset_standings()

        self.assertEqual(league.player(0).name, "Alice")
        self.assertTrue(
            all(player.rating == INITIAL_RATING for player in league.players)
        )
        self.assertEqual(league.matches, [])
        self.assertTrue(all(record == (0, 0) for record in league.records().values()))

    def test_reset_messages_use_the_configured_base_elo(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        app.league = app.collection.active.league
        app.league.base_elo = 1200.0
        app.league.record_match(0, 1, 0)
        app.root = Mock()
        app.status_var = Mock()
        app._ask_yes_no = Mock(return_value=True)
        app._commit_edit = Mock()
        app._refresh_all = Mock()
        app._show_error = Mock()

        app._reset_league()

        self.assertIn("1200.00", app._ask_yes_no.call_args.args[1])
        self.assertIn("1200.00", app._commit_edit.call_args.args[2])
        self.assertIn("1200.00", app.status_var.set.call_args.args[0])
        self.assertTrue(
            all(player.rating == 1200.0 for player in app.league.players)
        )

    def test_persistence_round_trip(self) -> None:
        league = League.new()
        league.rename_player(0, "Alice")
        league.record_match(0, 1, 1)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "league.json"
            league.save(path)
            restored = League.load(path)

        self.assertEqual(restored.player(0).name, "Alice")
        self.assertAlmostEqual(restored.player(0).rating, 1512.0)
        self.assertAlmostEqual(restored.player(1).rating, 1488.0)
        self.assertEqual(len(restored.matches), 1)

    def test_league_elo_settings_persist_and_are_stored_per_match(self) -> None:
        league = League.new(2)
        league.k_factor = 24.0
        league.elo_decimal_places = 1

        match = league.record_match(0, 1, 1)
        restored = League.from_dict(league.to_dict())

        self.assertEqual(match.rating_change, round(match.rating_change, 1))
        self.assertEqual(restored.k_factor, 24.0)
        self.assertEqual(restored.elo_decimal_places, 1)
        self.assertEqual(restored.matches[0].k_factor, 24.0)
        self.assertEqual(restored.matches[0].elo_decimal_places, 1)

    def test_schema_five_migrates_default_elo_settings(self) -> None:
        league = League.new(2)
        league.record_match(0, 1, 0)
        data = league.to_dict()
        data["schema_version"] = 5
        data.pop("k_factor")
        data.pop("elo_decimal_places")
        data["matches"][0].pop("k_factor")
        data["matches"][0].pop("elo_decimal_places")

        restored = League.from_dict(data)

        self.assertEqual(restored.k_factor, K_FACTOR)
        self.assertEqual(
            restored.elo_decimal_places, DEFAULT_ELO_DECIMAL_PLACES
        )
        self.assertEqual(restored.matches[0].k_factor, K_FACTOR)
        self.assertIsNone(restored.matches[0].elo_decimal_places)

    def test_new_league_has_twelve_players_at_1500(self) -> None:
        league = League.new()
        self.assertEqual(len(league.players), 12)
        self.assertTrue(
            all(player.rating == INITIAL_RATING for player in league.players)
        )

    def test_eight_player_save_is_migrated_without_losing_results(self) -> None:
        legacy_league = League.new()
        legacy_league.players = legacy_league.players[:8]
        legacy_league.rename_player(0, "Alice")
        legacy_league.record_match(0, 1, 1)

        legacy_data = legacy_league.to_dict()
        legacy_data["schema_version"] = 1
        migrated = League.from_dict(legacy_data)

        self.assertEqual(len(migrated.players), 12)
        self.assertEqual(migrated.player(0).name, "Alice")
        self.assertAlmostEqual(migrated.player(0).rating, 1512.0)
        self.assertEqual(len(migrated.matches), 1)
        self.assertEqual(migrated.players[-1].name, "Player 12")

    def test_invalid_match_is_rejected(self) -> None:
        league = League.new()
        with self.assertRaises(ValueError):
            league.record_match(0, 0, 2)
        with self.assertRaises(ValueError):
            league.record_match(0, 1, 3)
        with self.assertRaises(ValueError):
            league.record_match(0, 1, True)

    def test_custom_rules_reject_invalid_values(self) -> None:
        valid = {0: 1.0, 1: 0.75, 2: 0.5}
        for games_to_win in (0, 101, True):
            with self.subTest(games_to_win=games_to_win):
                with self.assertRaises(ValueError):
                    WinCondition(games_to_win, valid)

        for multiplier in (float("nan"), float("inf"), -0.1, True):
            with self.subTest(multiplier=multiplier):
                invalid = {0: multiplier, 1: 0.75, 2: 0.5}
                with self.assertRaises(ValueError):
                    WinCondition(3, invalid)
                with self.assertRaises(ValueError):
                    rating_change(1500.0, 1500.0, multiplier)

    def test_unrated_matches_remain_unrated_when_roster_is_replayed(self) -> None:
        league = League.new(4)
        league.calculate_elo = False
        match = league.record_match(0, 1, 0)

        league.resize_players(3)

        self.assertFalse(match.rated)
        self.assertEqual(league.matches[0].rating_change, 0.0)
        self.assertFalse(league.matches[0].rated)
        self.assertEqual(league.player(0).rating, INITIAL_RATING)
        self.assertEqual(league.player(1).rating, INITIAL_RATING)

    def test_custom_winner_score_is_persisted_and_counted(self) -> None:
        league = League.new(2)
        league.win_condition = WinCondition(
            5, {0: 1.0, 1: 0.9, 2: 0.8, 3: 0.7, 4: 0.6}
        )
        match = league.record_match(0, 1, 4)

        restored = League.from_dict(league.to_dict())
        stats = restored.statistics()

        self.assertEqual(match.winner_games, 5)
        self.assertEqual(restored.matches[0].winner_games, 5)
        self.assertEqual((stats[0].games_won, stats[0].games_lost), (5, 4))

    def test_custom_scores_scale_margin_and_persist(self) -> None:
        league = League.new(2)
        league.win_condition = WinCondition(score_mode=SCORE_MODE_CUSTOM)

        self.assertAlmostEqual(league.win_condition.get_multiplier(0, 3), 1.0)
        self.assertAlmostEqual(league.win_condition.get_multiplier(1, 3), 0.75)
        self.assertAlmostEqual(league.win_condition.get_multiplier(2, 3), 0.50)
        self.assertAlmostEqual(league.win_condition.get_multiplier(9, 10), 0.50)

        match = league.record_match(0, 1, 7, winner_games=11)
        restored = League.from_dict(league.to_dict())
        stats = restored.statistics()

        self.assertEqual((match.winner_games, match.loser_games), (11, 7))
        self.assertEqual(restored.win_condition.score_mode, SCORE_MODE_CUSTOM)
        self.assertEqual((stats[0].games_won, stats[0].games_lost), (11, 7))
        self.assertAlmostEqual(match.multiplier, 0.65)

    def test_custom_scores_reject_ties_losses_and_out_of_range_values(self) -> None:
        rules = WinCondition(score_mode=SCORE_MODE_CUSTOM)
        for winner_games, loser_games in (
            (3, 3),
            (2, 3),
            (0, 0),
            (3, -1),
            (True, 0),
            (MAX_CUSTOM_SCORE + 1, 0),
        ):
            with self.subTest(
                winner_games=winner_games, loser_games=loser_games
            ):
                with self.assertRaises(ValueError):
                    rules.get_multiplier(loser_games, winner_games)

    def test_schema_four_league_defaults_to_fixed_target_scores(self) -> None:
        data = League.new(2).to_dict()
        data["schema_version"] = 4
        data["win_condition"].pop("score_mode")

        restored = League.from_dict(data)

        self.assertEqual(restored.win_condition.score_mode, SCORE_MODE_FIXED)
        with self.assertRaises(ValueError):
            restored.win_condition.get_multiplier(1, 4)

    def test_invalid_historical_winner_score_is_rejected(self) -> None:
        league = League.new(2)
        league.record_match(0, 1, 0)
        data = league.to_dict()

        for winner_games in ("three", 0, True):
            with self.subTest(winner_games=winner_games):
                data["matches"][0]["winner_games"] = winner_games
                with self.assertRaises(ValueError):
                    League.from_dict(data)

        data["matches"][0]["winner_games"] = MAX_CUSTOM_SCORE + 1
        with self.assertRaises(ValueError):
            League.from_dict(data)

    def test_malformed_saved_match_and_rating_fields_are_rejected(self) -> None:
        data = League.new().to_dict()
        data["players"][0]["rating"] = True
        with self.assertRaises(ValueError):
            League.from_dict(data)

        data = League.new().to_dict()
        data["matches"] = [{
            "timestamp": None,
            "winner_id": [],
            "loser_id": 1,
            "loser_games": 0,
            "rating_change": "bad",
            "winner_rating_before": float("nan"),
            "loser_rating_before": 1500.0,
        }]
        with self.assertRaises(ValueError):
            League.from_dict(data)

    def test_application_instance_lock_is_exclusive_and_reusable(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "app.lock"
            first = ApplicationInstanceLock(path)
            second = ApplicationInstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.release()
                self.assertTrue(second.acquire())
            finally:
                first.release()
                second.release()

    def test_theme_preference_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load_theme(path), "light")
            save_theme(path, "dark")
            self.assertEqual(load_theme(path), "dark")

    def test_invalid_theme_file_falls_back_to_light(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"theme": "neon"}', encoding="utf-8")
            self.assertEqual(load_theme(path), "light")

    def test_malformed_preferences_fall_back_safely(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_bytes(b"\xff")
            self.assertEqual(load_app_settings(path), {})
            self.assertEqual(load_theme(path), "light")
            self.assertEqual(
                load_visible_columns(path),
                list(STANDINGS_COLUMN_IDS),
            )

            path.write_text(
                '{"theme": [], "visible_columns": [{}, "player", "player"]}',
                encoding="utf-8",
            )
            self.assertEqual(load_theme(path), "light")
            self.assertEqual(load_visible_columns(path), ["player"])

    def test_column_selection_fallback_and_save_failure_are_handled(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.column_vars = {
            column: Mock(get=Mock(return_value=False))
            for column in STANDINGS_COLUMN_IDS
        }
        app.standings = Mock()
        app.root = Mock()
        app.status_var = Mock()
        app._show_warning = Mock()

        with patch(
            "elo_calculator.save_visible_columns",
            side_effect=OSError("read only"),
        ):
            app._update_columns()

        self.assertEqual(app.visible_columns, ["player"])
        app.column_vars["player"].set.assert_called_once_with(True)
        app.standings.configure.assert_called_once_with(
            displaycolumns=["player"]
        )
        app._show_warning.assert_called_once()
        self.assertIn("not saved", app.status_var.set.call_args.args[0])

    def test_multiple_leagues_keep_independent_ratings_and_history(self) -> None:
        collection = LeagueCollection.new()
        first_id = collection.active.id
        collection.active.league.rename_player(0, "Alice")
        collection.active.league.record_match(0, 1, 0)

        second = collection.create_league("Tuesday League")
        second.league.rename_player(0, "Bob")
        second.league.record_match(1, 0, 2)

        collection.switch_to(first_id)
        self.assertEqual(collection.active.league.player(0).name, "Alice")
        self.assertAlmostEqual(collection.active.league.player(0).rating, 1516.0)
        self.assertEqual(len(collection.active.league.matches), 1)
        collection.switch_to(second.id)
        self.assertEqual(collection.active.league.player(0).name, "Bob")
        self.assertAlmostEqual(collection.active.league.player(0).rating, 1492.0)

    def test_single_league_save_migrates_to_collection(self) -> None:
        league = League.new()
        league.rename_player(0, "Alice")
        league.record_match(0, 1, 1)

        legacy_data = league.to_dict()
        legacy_data["schema_version"] = 1
        collection = LeagueCollection.from_dict(legacy_data)

        self.assertTrue(collection.migrated_from_single_league)
        self.assertEqual(len(collection.leagues), 1)
        self.assertEqual(collection.active.league.player(0).name, "Alice")
        self.assertEqual(len(collection.active.league.matches), 1)

    def test_collection_persistence_round_trip(self) -> None:
        collection = LeagueCollection.new()
        collection.create_league("Second League")
        collection.active.league.record_match(2, 3, 2)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "leagues.json"
            collection.save(path)
            restored = LeagueCollection.load(path)

        self.assertEqual(len(restored.leagues), 2)
        self.assertEqual(restored.active.name, "Second League")
        self.assertEqual(len(restored.active.league.matches), 1)

    def test_malformed_collection_name_raises_value_error(self) -> None:
        data = LeagueCollection.new().to_dict()
        data["leagues"][0]["name"] = 123
        with self.assertRaises(ValueError):
            LeagueCollection.from_dict(data)

        data = LeagueCollection.new().to_dict()
        data["active_league_id"] = []
        with self.assertRaises(ValueError):
            LeagueCollection.from_dict(data)

        data = LeagueCollection.new().to_dict()
        data["leagues"][0]["league"] = []
        with self.assertRaises(ValueError):
            LeagueCollection.from_dict(data)

    def test_non_object_collection_is_rejected_with_value_error(self) -> None:
        for malformed in (None, [], "not a database"):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(ValueError, "JSON object"):
                    LeagueCollection.from_dict(malformed)

    def test_navigation_commit_does_not_create_recovery_backup(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        first_id = app.collection.active.id
        app.collection.create_league("Second League")
        previous_state = app.collection.to_dict()
        app.collection.switch_to(first_id)
        app.backups = Mock()
        app.audit_log = Mock()

        with TemporaryDirectory() as directory:
            data_file = Path(directory) / "leagues.json"
            with patch("elo_calculator.DATA_FILE", data_file):
                app._commit_edit(
                    previous_state,
                    "league_switched",
                    "Switched leagues.",
                    create_backup=False,
                )
            restored = LeagueCollection.load(data_file)

        app.backups.create.assert_not_called()
        self.assertEqual(restored.active_league_id, first_id)

    def test_audit_failure_does_not_undo_a_saved_edit(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        app.league = app.collection.active.league
        app.backups = Mock()
        app.audit_log = Mock()
        app.audit_log.append.side_effect = OSError("audit unavailable")
        app.data_save_block_reason = None
        app.root = Mock()
        app._show_warning = Mock()
        previous_state = app.collection.to_dict()
        app.league.rename_player(0, "Saved Name")

        with TemporaryDirectory() as directory:
            data_file = Path(directory) / "leagues.json"
            with patch("elo_calculator.DATA_FILE", data_file):
                app._commit_edit(
                    previous_state,
                    "player_renamed",
                    "Renamed player.",
                )
            restored = LeagueCollection.load(data_file)

        self.assertEqual(app.league.player(0).name, "Saved Name")
        self.assertEqual(restored.active.league.player(0).name, "Saved Name")
        app._show_warning.assert_called_once()

    def test_failed_recovery_backup_does_not_overwrite_unreadable_data(self) -> None:
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        app.league = app.collection.active.league
        app.backups = Mock()
        app.backups.create.side_effect = OSError("backup unavailable")
        app.audit_log = Mock()
        app.data_save_block_reason = "Original database was not preserved."
        app.root = Mock()
        app._show_warning = Mock()
        previous_state = app.collection.to_dict()
        app.league.rename_player(0, "Restored Name")

        with TemporaryDirectory() as directory:
            data_file = Path(directory) / "leagues.json"
            original = b"\xff{unreadable database"
            data_file.write_bytes(original)
            with patch("elo_calculator.DATA_FILE", data_file):
                with self.assertRaisesRegex(OSError, "backup unavailable"):
                    app._commit_edit(
                        previous_state,
                        "backup_restored",
                        "Restore backup.",
                        allow_recovery_overwrite=True,
                    )
            self.assertEqual(data_file.read_bytes(), original)

        self.assertEqual(app.league.player(0).name, "Player 1")
        app.audit_log.append.assert_not_called()

    def test_unreadable_database_is_preserved_byte_for_byte(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_file = root / "elo_league_data.json"
            original = b"\xff{damaged database"
            data_file.write_bytes(original)

            recovery_path = preserve_unreadable_database(
                data_file, root / "recovery"
            )

            self.assertEqual(data_file.read_bytes(), original)
            self.assertEqual(recovery_path.read_bytes(), original)
            self.assertEqual(recovery_path.parent, root / "recovery")

    def test_commit_is_blocked_when_unreadable_database_was_not_preserved(
        self,
    ) -> None:
        app = object.__new__(EloCalculatorApp)
        app.collection = LeagueCollection.new()
        app.league = app.collection.active.league
        app.backups = Mock()
        app.audit_log = Mock()
        app.data_save_block_reason = "Original database was not preserved."
        previous_state = app.collection.to_dict()

        with TemporaryDirectory() as directory:
            data_file = Path(directory) / "leagues.json"
            with patch("elo_calculator.DATA_FILE", data_file):
                with self.assertRaisesRegex(ValueError, "not preserved"):
                    app._commit_edit(
                        previous_state,
                        "player_renamed",
                        "Unsafe replacement attempt.",
                    )
            self.assertFalse(data_file.exists())

        app.backups.create.assert_not_called()
        app.audit_log.append.assert_not_called()

    def test_backup_restores_all_leagues(self) -> None:
        collection = LeagueCollection.new()
        collection.active.league.rename_player(0, "Before Backup")

        with TemporaryDirectory() as directory:
            backups = BackupManager(Path(directory) / "backups")
            backup = backups.create(collection, "manual-backup")
            collection.active.league.rename_player(0, "After Backup")
            collection.create_league("Extra League")
            restored = backups.restore(backup)

        self.assertEqual(len(restored.leagues), 1)
        self.assertEqual(restored.active.league.player(0).name, "Before Backup")

    def test_malformed_backup_json_is_ignored_and_cannot_be_restored(self) -> None:
        collection = LeagueCollection.new()
        with TemporaryDirectory() as directory:
            backups = BackupManager(Path(directory))
            backup = backups.create(collection, "manual")
            backup.path.write_text("[]", encoding="utf-8")

            self.assertEqual(backups.list(), [])
            with self.assertRaises(ValueError):
                backups.restore(backup)

    def test_invalid_utf8_data_and_backups_are_handled(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "leagues.json"
            database.write_bytes(b"\xff")
            with self.assertRaisesRegex(ValueError, "could not be read"):
                LeagueCollection.load(database)
            with self.assertRaisesRegex(ValueError, "could not be read"):
                League.load(database)

            backups = BackupManager(root / "backups")
            backup = backups.create(LeagueCollection.new(), "manual")
            backup.path.write_bytes(b"\xff")
            self.assertEqual(backups.list(), [])
            with self.assertRaisesRegex(ValueError, "could not be read"):
                backups.restore(backup)

    def test_backup_pruning_protects_new_and_selected_snapshots(self) -> None:
        collection = LeagueCollection.new()
        with TemporaryDirectory() as directory:
            backups = BackupManager(Path(directory), max_backups=1)
            future = backups.create(collection, "future")
            future_path = future.path.with_name("99999999-future.json")
            future.path.replace(future_path)

            current = backups.create(collection, "current")

            self.assertTrue(current.path.exists())
            self.assertFalse(future_path.exists())

        with TemporaryDirectory() as directory:
            backups = BackupManager(Path(directory), max_backups=2)
            selected = backups.create(collection, "selected")
            selected_path = selected.path.with_name("00000000-selected.json")
            selected.path.replace(selected_path)
            obsolete = backups.create(collection, "obsolete")

            newest = backups.create(
                collection,
                "newest",
                protected_paths=(selected_path,),
            )

            self.assertTrue(selected_path.exists())
            self.assertTrue(newest.path.exists())
            self.assertFalse(obsolete.path.exists())
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)

        with self.assertRaisesRegex(ValueError, "At least one backup"):
            BackupManager(Path("unused"), max_backups=0)

    def test_audit_log_is_append_only_and_tracks_leagues(self) -> None:
        with TemporaryDirectory() as directory:
            log = AuditLog(Path(directory) / "audit.jsonl")
            log.append("player_renamed", "league-1", "Friday", "A to Alice")
            log.append("league_reset", "league-1", "Friday", "Cleared 4 matches")
            entries = log.read()

        self.assertEqual([entry["action"] for entry in entries], [
            "player_renamed", "league_reset"
        ])
        self.assertTrue(all(entry["league_name"] == "Friday" for entry in entries))

    def test_audit_log_skips_invalid_utf8_and_honors_tail_limit(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            log = AuditLog(path)
            for index in range(20):
                log.append("event", "league-1", "Friday", str(index))
            with path.open("ab") as file:
                file.write(b"\xff\n")
            log.append("event", "league-1", "Friday", "last")

            entries = log.read(limit=3)

        self.assertEqual(
            [entry["details"] for entry in entries],
            ["19", "last"],
        )

    def test_only_league_cannot_be_deleted(self) -> None:
        collection = LeagueCollection.new()
        with self.assertRaises(ValueError):
            collection.delete_league(collection.active.id)

    def test_new_league_accepts_adjustable_player_count(self) -> None:
        league = League.new(20)
        self.assertEqual(len(league.players), 20)
        self.assertTrue(all(player.rating == INITIAL_RATING for player in league.players))
        with self.assertRaises(ValueError):
            League.new(MIN_PLAYER_COUNT - 1)
        with self.assertRaises(ValueError):
            League.new(MAX_PLAYER_COUNT + 1)

    def test_increasing_player_count_preserves_existing_league(self) -> None:
        league = League.new(4)
        league.rename_player(0, "Alice")
        league.record_match(0, 1, 1)
        alice_rating = league.player(0).rating

        result = league.resize_players(7)

        self.assertEqual(len(league.players), 7)
        self.assertEqual(league.player(0).name, "Alice")
        self.assertAlmostEqual(league.player(0).rating, alice_rating)
        self.assertEqual(len(league.matches), 1)
        self.assertEqual(result["added"], ["Player 5", "Player 6", "Player 7"])

    def test_decreasing_player_count_removes_related_matches_and_replays(self) -> None:
        league = League.new(6)
        league.record_match(0, 1, 0)
        league.record_match(5, 0, 0)
        league.record_match(1, 2, 2)

        expected = League.new(4)
        expected.record_match(0, 1, 0)
        expected.record_match(1, 2, 2)
        result = league.resize_players(4)

        self.assertEqual(len(league.players), 4)
        self.assertEqual(len(league.matches), 2)
        self.assertEqual(result["removed_match_count"], 1)
        for player in league.players:
            self.assertAlmostEqual(player.rating, expected.player(player.id).rating)

    def test_roster_replay_uses_historical_match_elo_settings(self) -> None:
        league = League.new(4)
        league.k_factor = 16.0
        league.elo_decimal_places = 0
        retained = league.record_match(0, 1, 0)
        expected_ratings = (
            league.player(0).rating,
            league.player(1).rating,
        )

        league.k_factor = 64.0
        league.elo_decimal_places = 2
        league.record_match(3, 0, 0)
        league.resize_players(3)

        replayed = league.matches[0]
        self.assertEqual(replayed.k_factor, retained.k_factor)
        self.assertEqual(
            replayed.elo_decimal_places, retained.elo_decimal_places
        )
        self.assertEqual(league.player(0).rating, expected_ratings[0])
        self.assertEqual(league.player(1).rating, expected_ratings[1])

    def test_failed_roster_replay_does_not_partially_mutate_league(self) -> None:
        league = League.new(3)
        league.record_match(0, 1, 0)
        league.matches[0].multiplier = 1e308
        state_before = league.to_dict()

        with self.assertRaisesRegex(ValueError, "Rating change must be finite"):
            league.resize_players(2)

        self.assertEqual(league.to_dict(), state_before)

    def test_adjustable_player_count_persists_per_league(self) -> None:
        collection = LeagueCollection.new()
        collection.active.league.resize_players(8)
        second = collection.create_league("Large League", 24)

        restored = LeagueCollection.from_dict(collection.to_dict())

        self.assertEqual(len(restored.leagues[0].league.players), 8)
        self.assertEqual(len(restored.by_id(second.id).league.players), 24)

    def test_previous_multi_league_database_upgrades_to_variable_rosters(self) -> None:
        collection = LeagueCollection.new()
        previous_data = collection.to_dict()
        previous_data["leagues"][0]["league"]["schema_version"] = 1

        upgraded = LeagueCollection.from_dict(previous_data)

        self.assertEqual(len(upgraded.active.league.players), 12)
        self.assertEqual(
            upgraded.active.league.to_dict()["schema_version"],
            LEAGUE_SCHEMA_VERSION,
        )


class RegressionTests(unittest.TestCase):
    def test_resize_players_retains_scaled_k_factor_and_base_elo(self) -> None:
        league = League.new(3)
        league.base_elo = 1000.0
        league.k_factor_scaling = True
        league.reset_standings()

        # Play a match with scaling (3-0 sweep)
        match = league.record_match(0, 1, 0, 3)

        # Base multiplier is 1.0, difference is 3 games. 
        # scaled multiplier = 1.0 * (1 + 3 * 0.1) = 1.3
        self.assertAlmostEqual(match.multiplier, 1.3)
        
        # Verify rating before resize
        p0_rating = league.player(0).rating
        p1_rating = league.player(1).rating
        self.assertAlmostEqual(p0_rating, 1020.8)
        self.assertAlmostEqual(p1_rating, 979.2)

        # Resize to trigger replay
        league.resize_players(2)

        # Verify ratings remained stable and didn't shift to INITIAL_RATING
        # or lose the scaling multiplier.
        self.assertAlmostEqual(league.player(0).rating, p0_rating)
        self.assertAlmostEqual(league.player(1).rating, p1_rating)


if __name__ == "__main__":
    unittest.main()


# Purpose: Regression tests for Elo rules, persistence, storage, and migrations.
# Upstream: elo_model.py, elo_storage.py, and selected application helpers.
# Upstream purpose: Implement the desktop league calculator and durable data model.
# Environment: Python 3.10+ unittest suite on Windows.
# Generated: 2026-09-09 07:43 America/New_York.
# Changes: Covers schema-8 settings validation, base/scaled replay, simulator
# scaling, recovery transaction safety, bounded/corrupt auxiliary reads, exact Elo
# graph starts, column preferences, standings labels, and configurable reset text.
# Changed lines: 1-28 provenance/imports; 187-198 and 241-263 graph/menu cases;
# 499-654 settings/replay/scaling; 939-960 reset text; 1189-1231 preferences;
# 1324-1380 save/recovery failures; 1446-1525 backup/audit cases;
# 1623-1626 current schema assertion.

class RankHistoryTests(unittest.TestCase):
    def test_player_rank_history_evaluates_historical_tiebreakers(self) -> None:
        from elo_calculator import _player_rank_history
        league = League.new(3)
        league.player(0).name = 'Alice'
        league.player(1).name = 'Bob'
        league.player(2).name = 'Charlie'
        
        # Initial: All 1500. Alphabetical tiebreaker means Alice(1), Bob(2), Charlie(3)
        
        # Match 1: Alice sweeps Bob 3-0. 
        # Alice 1 (+), Bob 3 (-), Charlie 2
        league.record_match(0, 1, 0, 3)
        
        # Match 2: Charlie sweeps Alice 3-0.
        # Charlie goes way up. Alice goes down. 
        league.record_match(2, 0, 0, 3)
        
        alice_ranks = _player_rank_history(league, 0)
        bob_ranks = _player_rank_history(league, 1)
        charlie_ranks = _player_rank_history(league, 2)
        
        self.assertEqual(alice_ranks, [1, 1, 2])
        self.assertEqual(bob_ranks, [2, 3, 3])
        self.assertEqual(charlie_ranks, [3, 2, 1])

