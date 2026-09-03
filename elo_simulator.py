"""Read-only Monte Carlo simulation for First-to-N Elo leagues."""

from __future__ import annotations

from dataclasses import dataclass
import random

from elo_model import League, SCORE_MODE_FIXED, expected_score, rating_change


MAX_SIMULATIONS = 10_000
MAX_GAME_TRIALS = 10_000_000


@dataclass(frozen=True)
class PlayerSimulationResult:
    player_id: int
    name: str
    title_probability: float
    average_rank: float
    average_matches_won: float
    average_matches_lost: float
    average_games_won: float
    average_games_lost: float


@dataclass(frozen=True)
class LeagueSimulationResult:
    simulations: int
    games_to_win: int
    matches_per_simulation: int
    players: tuple[PlayerSimulationResult, ...]


@dataclass(frozen=True)
class SimulatedMatch:
    winner_id: int
    loser_id: int
    winner_games: int
    loser_games: int


def simulation_limit(player_count: int, games_to_win: int = 3) -> int:
    """Return a safe simulation limit for the given round-robin size."""
    if not isinstance(player_count, int) or isinstance(player_count, bool):
        raise ValueError("Player count must be a whole number.")
    if player_count < 2:
        raise ValueError("At least two players are required for a simulation.")
    if (
        not isinstance(games_to_win, int)
        or isinstance(games_to_win, bool)
        or games_to_win < 1
    ):
        raise ValueError("Games to win must be a positive whole number.")
    pair_count = player_count * (player_count - 1) // 2
    maximum_games_per_match = 2 * games_to_win - 1
    return min(
        MAX_SIMULATIONS,
        max(
            1,
            MAX_GAME_TRIALS // (pair_count * maximum_games_per_match),
        ),
    )


def simulate_first_to_n_season(
    league: League,
    seed: int | None = None,
) -> tuple[SimulatedMatch, ...]:
    """Generate one concrete round-robin season without modifying the league."""
    if league.win_condition.score_mode != SCORE_MODE_FIXED:
        raise ValueError("The league simulator supports First to N format only.")
    if seed is not None and (
        not isinstance(seed, int) or isinstance(seed, bool)
    ):
        raise ValueError("Random seed must be a whole number or blank.")

    players = tuple(league.players)
    games_to_win = league.win_condition.games_to_win
    ratings = [player.rating for player in players]
    pairings = [
        (first, second)
        for first in range(len(players))
        for second in range(first + 1, len(players))
    ]
    rng = random.Random(seed)
    rng.shuffle(pairings)
    matches: list[SimulatedMatch] = []

    for first, second in pairings:
        first_probability = expected_score(ratings[first], ratings[second])
        first_games = 0
        second_games = 0
        while first_games < games_to_win and second_games < games_to_win:
            if rng.random() < first_probability:
                first_games += 1
            else:
                second_games += 1

        if first_games == games_to_win:
            winner, loser = first, second
            loser_games = second_games
        else:
            winner, loser = second, first
            loser_games = first_games
        matches.append(
            SimulatedMatch(
                winner_id=players[winner].id,
                loser_id=players[loser].id,
                winner_games=games_to_win,
                loser_games=loser_games,
            )
        )

        if league.calculate_elo:
            multiplier = league.win_condition.get_multiplier(
                loser_games, games_to_win
            )
            change = rating_change(
                ratings[winner],
                ratings[loser],
                multiplier,
                league.k_factor,
                league.elo_decimal_places,
            )
            ratings[winner] += change
            ratings[loser] -= change

    return tuple(matches)


def simulate_first_to_n_league(
    league: League,
    simulations: int = 2_000,
    seed: int | None = None,
) -> LeagueSimulationResult:
    """Simulate single round-robin seasons without modifying the league."""
    if league.win_condition.score_mode != SCORE_MODE_FIXED:
        raise ValueError("The league simulator supports First to N format only.")
    maximum = simulation_limit(
        len(league.players), league.win_condition.games_to_win
    )
    if (
        not isinstance(simulations, int)
        or isinstance(simulations, bool)
        or not 1 <= simulations <= maximum
    ):
        raise ValueError(
            f"Simulations must be a whole number between 1 and {maximum}."
        )
    if seed is not None and (
        not isinstance(seed, int) or isinstance(seed, bool)
    ):
        raise ValueError("Random seed must be a whole number or blank.")

    players = tuple(league.players)
    player_count = len(players)
    games_to_win = league.win_condition.games_to_win
    pairings = [
        (first, second)
        for first in range(player_count)
        for second in range(first + 1, player_count)
    ]
    rng = random.Random(seed)

    title_counts = [0.0] * player_count
    rank_totals = [0.0] * player_count
    match_win_totals = [0] * player_count
    match_loss_totals = [0] * player_count
    game_win_totals = [0] * player_count
    game_loss_totals = [0] * player_count

    for _simulation_number in range(simulations):
        ratings = [player.rating for player in players]
        match_wins = [0] * player_count
        match_losses = [0] * player_count
        game_wins = [0] * player_count
        game_losses = [0] * player_count
        winners_and_losers: list[tuple[int, int]] = []
        season_pairings = pairings.copy()
        rng.shuffle(season_pairings)

        for first, second in season_pairings:
            first_probability = expected_score(ratings[first], ratings[second])
            first_games = 0
            second_games = 0
            while (
                first_games < games_to_win and second_games < games_to_win
            ):
                if rng.random() < first_probability:
                    first_games += 1
                else:
                    second_games += 1

            if first_games == games_to_win:
                winner, loser = first, second
                loser_games = second_games
            else:
                winner, loser = second, first
                loser_games = first_games

            match_wins[winner] += 1
            match_losses[loser] += 1
            game_wins[first] += first_games
            game_losses[first] += second_games
            game_wins[second] += second_games
            game_losses[second] += first_games
            winners_and_losers.append((winner, loser))

            if league.calculate_elo:
                multiplier = league.win_condition.get_multiplier(
                    loser_games, games_to_win
                )
                change = rating_change(
                    ratings[winner],
                    ratings[loser],
                    multiplier,
                    league.k_factor,
                    league.elo_decimal_places,
                )
                ratings[winner] += change
                ratings[loser] -= change

        sb_scores = [0] * player_count
        for winner, loser in winners_and_losers:
            sb_scores[winner] += match_wins[loser]

        def standing_key(index: int) -> tuple[int, int, int, int, float]:
            return (
                -match_wins[index],
                -sb_scores[index],
                -(game_wins[index] - game_losses[index]),
                -game_wins[index],
                -ratings[index],
            )

        order = sorted(
            range(player_count),
            key=lambda index: (standing_key(index), players[index].id),
        )
        group_start = 0
        while group_start < player_count:
            group_end = group_start + 1
            while (
                group_end < player_count
                and standing_key(order[group_end])
                == standing_key(order[group_start])
            ):
                group_end += 1
            tied_players = order[group_start:group_end]
            average_rank = (group_start + 1 + group_end) / 2.0
            for index in tied_players:
                rank_totals[index] += average_rank
            if group_start == 0:
                title_share = 1.0 / len(tied_players)
                for index in tied_players:
                    title_counts[index] += title_share
            group_start = group_end

        for index in order:
            match_win_totals[index] += match_wins[index]
            match_loss_totals[index] += match_losses[index]
            game_win_totals[index] += game_wins[index]
            game_loss_totals[index] += game_losses[index]

    results = tuple(
        sorted(
            (
                PlayerSimulationResult(
                    player_id=player.id,
                    name=player.name,
                    title_probability=100.0 * title_counts[index] / simulations,
                    average_rank=rank_totals[index] / simulations,
                    average_matches_won=match_win_totals[index] / simulations,
                    average_matches_lost=match_loss_totals[index] / simulations,
                    average_games_won=game_win_totals[index] / simulations,
                    average_games_lost=game_loss_totals[index] / simulations,
                )
                for index, player in enumerate(players)
            ),
            key=lambda result: (
                -result.title_probability,
                result.average_rank,
                result.player_id,
            ),
        )
    )
    return LeagueSimulationResult(
        simulations=simulations,
        games_to_win=games_to_win,
        matches_per_simulation=len(pairings),
        players=results,
    )


# Purpose: Simulate complete First-to-N round-robin seasons without saved edits.
# Upstream: elo_model.py supplies league rules, ratings, and Elo calculations.
# Upstream purpose: Represent validated leagues and persistent match results.
# Environment: Python 3.10+ on Windows or any platform supported by the model.
# Generated: 2026-09-03 08:31 America/New_York.
# Changes: Adds reproducible concrete round-robin seasons that can be recorded
# through the application's normal persistence, backup, and audit path.
