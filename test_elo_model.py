"""Tests for the Elo league rules."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from elo_calculator import (
    ApplicationInstanceLock,
    EloCalculatorApp,
    THEME_PALETTES,
    load_theme,
    save_theme,
)
from elo_model import (
    DEFAULT_ELO_DECIMAL_PLACES,
    INITIAL_RATING,
    K_FACTOR,
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
        self.assertEqual(upgraded.active.league.to_dict()["schema_version"], 7)


if __name__ == "__main__":
    unittest.main()


# Purpose: Regression tests for Elo rules, persistence, storage, and migrations.
# Upstream: elo_model.py, elo_storage.py, and selected application helpers.
# Upstream purpose: Implement the desktop league calculator and durable data model.
# Environment: Python 3.10+ unittest suite on Windows.
# Generated: 2026-09-03 08:31 America/New_York.
# Changes: Covers concrete simulated-season recording and light/dark graph
# palette selection alongside simulator, Elo, draw, persistence, and UI rules.
