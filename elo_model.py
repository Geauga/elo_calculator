# elo_model.py
# Request: Review and patch league settings, historical replay, and persistence.
"""Core Elo rules and persistence for leagues with adjustable rosters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_PLAYER_COUNT = 12
# Kept as an alias for compatibility with earlier imports.
PLAYER_COUNT = DEFAULT_PLAYER_COUNT
LEGACY_PLAYER_COUNT = 8
MIN_PLAYER_COUNT = 2
MAX_PLAYER_COUNT = 64
LEAGUE_SCHEMA_VERSION = 8
INITIAL_RATING = 1500.0
K_FACTOR = 32.0
MIN_K_FACTOR = 0.01
MAX_K_FACTOR = 1000.0
DEFAULT_ELO_DECIMAL_PLACES = 2
MAX_ELO_DECIMAL_PLACES = 6
SCORE_MULTIPLIERS = {0: 1.0, 1: 0.75, 2: 0.50}
MAX_GAMES_TO_WIN = 100
MAX_CUSTOM_SCORE = 9999
SCORE_MODE_FIXED = "fixed_target"
SCORE_MODE_CUSTOM = "custom"
SCORE_MODES = (SCORE_MODE_FIXED, SCORE_MODE_CUSTOM)
DEFAULT_TIEBREAKER_HIERARCHY = (
    "rating",
    "match_pct",
    "sb_score",
    "game_pct",
    "name",
)


@dataclass
class WinCondition:
    games_to_win: int = 3
    score_multipliers: dict[int, float] = field(default_factory=lambda: {0: 1.0, 1: 0.75, 2: 0.50})
    score_mode: str = SCORE_MODE_FIXED

    def __post_init__(self) -> None:
        if self.score_mode not in SCORE_MODES:
            raise ValueError("Score format must be fixed-target or custom.")
        if (
            not isinstance(self.games_to_win, int)
            or isinstance(self.games_to_win, bool)
            or not 1 <= self.games_to_win <= MAX_GAMES_TO_WIN
        ):
            raise ValueError(
                f"Games to win must be between 1 and {MAX_GAMES_TO_WIN}."
            )
        if not isinstance(self.score_multipliers, dict):
            raise ValueError("Score multipliers must be a mapping.")

        normalized: dict[int, float] = {}
        for loser_games in range(self.games_to_win):
            multiplier = self.score_multipliers.get(loser_games, 1.0)
            if (
                not isinstance(multiplier, (int, float))
                or isinstance(multiplier, bool)
                or not math.isfinite(multiplier)
                or multiplier < 0
            ):
                raise ValueError(
                    "Score multipliers must be finite, nonnegative numbers."
                )
            normalized[loser_games] = float(multiplier)
        if any(
            not isinstance(key, int)
            or isinstance(key, bool)
            or key not in normalized
            for key in self.score_multipliers
        ):
            raise ValueError("Every multiplier score must be a valid losing score.")
        self.score_multipliers = normalized

    def get_multiplier(
        self, loser_games: int, winner_games: int | None = None
    ) -> float:
        if winner_games is None:
            winner_games = self.games_to_win
        if self.score_mode == SCORE_MODE_CUSTOM:
            validate_custom_score(winner_games, loser_games)
            if winner_games == 1:
                return 1.0
            # A shutout uses the full Elo change and the closest possible win
            # uses half. Scores between those endpoints scale proportionally.
            return 1.0 - loser_games / (2.0 * (winner_games - 1))
        if winner_games != self.games_to_win:
            raise ValueError(
                f"The winner must score {self.games_to_win} in this league."
            )
        if not isinstance(loser_games, int) or isinstance(loser_games, bool) or loser_games < 0 or loser_games >= self.games_to_win:
            raise ValueError(f"Loser games must be between 0 and {self.games_to_win - 1}.")
        return self.score_multipliers.get(loser_games, 1.0)


def validate_custom_score(winner_games: int, loser_games: int) -> None:
    for score in (winner_games, loser_games):
        if not isinstance(score, int) or isinstance(score, bool):
            raise ValueError("Final scores must be whole numbers.")
    if not 1 <= winner_games <= MAX_CUSTOM_SCORE:
        raise ValueError(
            f"Winner score must be between 1 and {MAX_CUSTOM_SCORE}."
        )
    if not 0 <= loser_games < winner_games:
        raise ValueError("Winner score must be greater than loser score.")


def validate_player_count(player_count: int) -> int:
    if not isinstance(player_count, int) or isinstance(player_count, bool):
        raise ValueError("Player count must be a whole number.")
    if not MIN_PLAYER_COUNT <= player_count <= MAX_PLAYER_COUNT:
        raise ValueError(
            f"Player count must be between {MIN_PLAYER_COUNT} and "
            f"{MAX_PLAYER_COUNT}."
        )
    return player_count


def validate_k_factor(k_factor: float) -> float:
    if (
        not isinstance(k_factor, (int, float))
        or isinstance(k_factor, bool)
        or not math.isfinite(k_factor)
        or not MIN_K_FACTOR <= k_factor <= MAX_K_FACTOR
    ):
        raise ValueError(
            f"K-factor must be between {MIN_K_FACTOR:g} and "
            f"{MAX_K_FACTOR:g}."
        )
    return float(k_factor)


def validate_elo_decimal_places(decimal_places: int | None) -> int | None:
    if decimal_places is None:
        return None
    if (
        not isinstance(decimal_places, int)
        or isinstance(decimal_places, bool)
        or not 0 <= decimal_places <= MAX_ELO_DECIMAL_PLACES
    ):
        raise ValueError(
            "Elo decimal places must be between 0 and "
            f"{MAX_ELO_DECIMAL_PLACES}."
        )
    return decimal_places


def validate_base_elo(base_elo: float) -> float:
    if (
        not isinstance(base_elo, (int, float))
        or isinstance(base_elo, bool)
        or not math.isfinite(base_elo)
    ):
        raise ValueError("Base Elo must be a finite number.")
    return float(base_elo)


def validate_tiebreaker_hierarchy(hierarchy: list[str]) -> list[str]:
    if (
        not isinstance(hierarchy, list)
        or len(hierarchy) != len(DEFAULT_TIEBREAKER_HIERARCHY)
        or any(not isinstance(item, str) for item in hierarchy)
        or set(hierarchy) != set(DEFAULT_TIEBREAKER_HIERARCHY)
    ):
        raise ValueError(
            "The tiebreaker hierarchy must contain each supported tiebreaker "
            "exactly once."
        )
    return list(hierarchy)


def expected_score(rating: float, opponent_rating: float) -> float:
    """Return the standard Elo expected score for one player."""
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for value in (rating, opponent_rating)
    ):
        raise ValueError("Ratings must be finite numbers.")
    exponent = max(-10.0, min(10.0, (opponent_rating - rating) / 400.0))
    return 1.0 / (1.0 + (10.0**exponent))


def rating_change(
    winner_rating: float,
    loser_rating: float,
    multiplier: float = 1.0,
    k_factor: float = K_FACTOR,
    decimal_places: int | None = None,
) -> float:
    """Return the Elo transferred."""
    if (
        not isinstance(multiplier, (int, float))
        or isinstance(multiplier, bool)
        or not math.isfinite(multiplier)
        or multiplier < 0
    ):
        raise ValueError("Multiplier must be a finite, nonnegative number.")

    validated_k_factor = validate_k_factor(k_factor)
    validated_decimal_places = validate_elo_decimal_places(decimal_places)
    change = validated_k_factor * multiplier * (
        1.0 - expected_score(winner_rating, loser_rating)
    )
    if not math.isfinite(change):
        raise ValueError("Rating change must be finite.")
    return (
        round(change, validated_decimal_places)
        if validated_decimal_places is not None
        else change
    )


def draw_rating_change(
    player_rating: float,
    opponent_rating: float,
    k_factor: float = K_FACTOR,
    decimal_places: int | None = None,
) -> float:
    """Return one player's signed Elo change for a draw."""
    validated_k_factor = validate_k_factor(k_factor)
    validated_decimal_places = validate_elo_decimal_places(decimal_places)
    change = validated_k_factor * (
        0.5 - expected_score(player_rating, opponent_rating)
    )
    if not math.isfinite(change):
        raise ValueError("Rating change must be finite.")
    return (
        round(change, validated_decimal_places)
        if validated_decimal_places is not None
        else change
    )


@dataclass
class Player:
    id: int
    name: str
    rating: float = INITIAL_RATING


@dataclass
class Match:
    timestamp: str
    winner_id: int
    loser_id: int
    loser_games: int
    rating_change: float
    winner_rating_before: float
    loser_rating_before: float
    multiplier: float = 0.0
    winner_games: int = 3
    rated: bool = True
    k_factor: float = K_FACTOR
    elo_decimal_places: int | None = None
    is_draw: bool = False


@dataclass
class PlayerStatistics:
    matches_won: int = 0
    matches_drawn: int = 0
    matches_lost: int = 0
    games_won: int = 0
    games_lost: int = 0
    sb_score: float = 0.0

    @property
    def match_win_percentage(self) -> float:
        total = self.matches_won + self.matches_drawn + self.matches_lost
        points = self.matches_won + 0.5 * self.matches_drawn
        return 100.0 * points / total if total else 0.0

    @property
    def game_win_percentage(self) -> float:
        total = self.games_won + self.games_lost
        return 100.0 * self.games_won / total if total else 0.0


@dataclass
class League:
    players: list[Player]
    matches: list[Match] = field(default_factory=list)
    win_condition: WinCondition = field(default_factory=WinCondition)
    calculate_elo: bool = True
    k_factor: float = K_FACTOR
    elo_decimal_places: int = DEFAULT_ELO_DECIMAL_PLACES
    allow_draws: bool = True
    base_elo: float = INITIAL_RATING
    k_factor_scaling: bool = False
    tiebreaker_hierarchy: list[str] = field(
        default_factory=lambda: list(DEFAULT_TIEBREAKER_HIERARCHY)
    )

    def __post_init__(self) -> None:
        self.k_factor = validate_k_factor(self.k_factor)
        validated_places = validate_elo_decimal_places(self.elo_decimal_places)
        if validated_places is None:
            raise ValueError("League Elo decimal places cannot be unlimited.")
        self.elo_decimal_places = validated_places
        if not isinstance(self.allow_draws, bool):
            raise ValueError("The allow-draws setting must be true or false.")
        self.base_elo = validate_base_elo(self.base_elo)
        if not isinstance(self.k_factor_scaling, bool):
            raise ValueError("The K-factor scaling setting must be true or false.")
        self.tiebreaker_hierarchy = validate_tiebreaker_hierarchy(
            self.tiebreaker_hierarchy
        )

    @classmethod
    def new(cls, player_count: int = DEFAULT_PLAYER_COUNT) -> "League":
        validate_player_count(player_count)
        return cls(
            players=[
                Player(id=index, name=f"Player {index + 1}")
                for index in range(player_count)
            ]
        )

    def player(self, player_id: int) -> Player:
        for player in self.players:
            if player.id == player_id:
                return player
        raise ValueError(f"Unknown player ID: {player_id}")

    def elo_multiplier(
        self, loser_games: int, winner_games: int | None = None
    ) -> float:
        """Return the complete score and optional K-scaling multiplier."""
        if winner_games is None:
            winner_games = self.win_condition.games_to_win
        multiplier = self.win_condition.get_multiplier(loser_games, winner_games)
        if self.k_factor_scaling:
            multiplier *= 1.0 + (winner_games - loser_games) * 0.1
        return multiplier

    def preview_match(
        self,
        winner_id: int,
        loser_id: int,
        loser_games: int,
        winner_games: int | None = None,
    ) -> dict[str, float]:
        if winner_id == loser_id:
            raise ValueError("Winner and loser must be different players.")

        winner = self.player(winner_id)
        loser = self.player(loser_id)
        if winner_games is None:
            winner_games = self.win_condition.games_to_win
        multiplier = self.win_condition.get_multiplier(loser_games, winner_games)
        elo_multiplier = self.elo_multiplier(loser_games, winner_games)
        change = (
            rating_change(
                winner.rating,
                loser.rating,
                elo_multiplier,
                self.k_factor,
                self.elo_decimal_places,
            )
            if self.calculate_elo
            else 0.0
        )
        winner_after = winner.rating + change
        loser_after = loser.rating - change
        if not math.isfinite(winner_after) or not math.isfinite(loser_after):
            raise ValueError("Resulting ratings must be finite.")
        return {
            "winner_expected": expected_score(winner.rating, loser.rating),
            "loser_expected": expected_score(loser.rating, winner.rating),
            "multiplier": multiplier,
            "elo_multiplier": elo_multiplier,
            "change": change,
            "winner_after": winner_after,
            "loser_after": loser_after,
        }

    def record_match(
        self,
        winner_id: int,
        loser_id: int,
        loser_games: int,
        winner_games: int | None = None,
    ) -> Match:
        if winner_games is None:
            winner_games = self.win_condition.games_to_win
        preview = self.preview_match(
            winner_id, loser_id, loser_games, winner_games
        )
        winner = self.player(winner_id)
        loser = self.player(loser_id)

        match = Match(
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            winner_id=winner_id,
            loser_id=loser_id,
            loser_games=loser_games,
            rating_change=preview["change"],
            winner_rating_before=winner.rating,
            loser_rating_before=loser.rating,
            multiplier=preview["elo_multiplier"],
            winner_games=winner_games,
            rated=self.calculate_elo,
            k_factor=self.k_factor,
            elo_decimal_places=self.elo_decimal_places,
        )
        winner.rating = preview["winner_after"]
        loser.rating = preview["loser_after"]
        self.matches.append(match)
        return match

    def preview_draw(self, player_one_id: int, player_two_id: int) -> dict[str, float]:
        if not self.allow_draws:
            raise ValueError("Draws are disabled for this league.")
        if player_one_id == player_two_id:
            raise ValueError("The two players must be different.")
        player_one = self.player(player_one_id)
        player_two = self.player(player_two_id)
        player_one_expected = expected_score(player_one.rating, player_two.rating)
        change = (
            draw_rating_change(
                player_one.rating,
                player_two.rating,
                self.k_factor,
                self.elo_decimal_places,
            )
            if self.calculate_elo
            else 0.0
        )
        player_one_after = player_one.rating + change
        player_two_after = player_two.rating - change
        if not math.isfinite(player_one_after) or not math.isfinite(player_two_after):
            raise ValueError("Resulting ratings must be finite.")
        return {
            "player_one_expected": player_one_expected,
            "player_two_expected": 1.0 - player_one_expected,
            "change": change,
            "player_one_after": player_one_after,
            "player_two_after": player_two_after,
        }

    def record_draw(self, player_one_id: int, player_two_id: int) -> Match:
        preview = self.preview_draw(player_one_id, player_two_id)
        player_one = self.player(player_one_id)
        player_two = self.player(player_two_id)
        match = Match(
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            winner_id=player_one_id,
            loser_id=player_two_id,
            loser_games=0,
            rating_change=preview["change"],
            winner_rating_before=player_one.rating,
            loser_rating_before=player_two.rating,
            multiplier=1.0,
            winner_games=0,
            rated=self.calculate_elo,
            k_factor=self.k_factor,
            elo_decimal_places=self.elo_decimal_places,
            is_draw=True,
        )
        player_one.rating = preview["player_one_after"]
        player_two.rating = preview["player_two_after"]
        self.matches.append(match)
        return match

    def undo_last_match(self) -> Match:
        if not self.matches:
            raise ValueError("There is no match to undo.")

        match = self.matches.pop()
        self.player(match.winner_id).rating = match.winner_rating_before
        self.player(match.loser_id).rating = match.loser_rating_before
        return match

    def reset_standings(self) -> None:
        """Reset ratings and records while retaining the player roster."""
        for player in self.players:
            player.rating = self.base_elo
        self.matches.clear()

    def resize_players(self, player_count: int) -> dict[str, Any]:
        """Resize the roster and consistently rebuild retained match results."""
        validate_player_count(player_count)
        old_count = len(self.players)
        if player_count == old_count:
            return {"added": [], "removed": [], "removed_match_count": 0}

        if player_count > old_count:
            existing_names = {player.name.casefold() for player in self.players}
            next_id = max((player.id for player in self.players), default=-1) + 1
            added: list[str] = []
            for roster_number in range(old_count + 1, player_count + 1):
                name = f"Player {roster_number}"
                while name.casefold() in existing_names:
                    name += " New"
                self.players.append(Player(id=next_id, name=name, rating=self.base_elo))
                existing_names.add(name.casefold())
                added.append(name)
                next_id += 1
            return {"added": added, "removed": [], "removed_match_count": 0}

        removed_players = self.players[player_count:]
        removed_ids = {player.id for player in removed_players}
        retained_matches = [
            match
            for match in self.matches
            if match.winner_id not in removed_ids and match.loser_id not in removed_ids
        ]
        removed_match_count = len(self.matches) - len(retained_matches)
        # Dropping a match changes the inputs to later Elo calculations. Replay
        # retained results in their original order so the remaining standings
        # are mathematically consistent rather than carrying ghost Elo. Keep
        # replay state local so a validation failure cannot partially mutate
        # the roster, ratings, or history.
        retained_players = self.players[:player_count]
        replayed_ratings = {player.id: player.rating for player in retained_players}
        unseen_player_ids = set(replayed_ratings)
        for old_match in self.matches:
            if old_match.winner_id in unseen_player_ids:
                replayed_ratings[old_match.winner_id] = (
                    old_match.winner_rating_before
                )
                unseen_player_ids.remove(old_match.winner_id)
            if old_match.loser_id in unseen_player_ids:
                replayed_ratings[old_match.loser_id] = old_match.loser_rating_before
                unseen_player_ids.remove(old_match.loser_id)
            if not unseen_player_ids:
                break
        rebuilt_matches: list[Match] = []
        for old_match in retained_matches:
            winner_rating = replayed_ratings[old_match.winner_id]
            loser_rating = replayed_ratings[old_match.loser_id]
            if old_match.is_draw:
                change = (
                    draw_rating_change(
                        winner_rating,
                        loser_rating,
                        old_match.k_factor,
                        old_match.elo_decimal_places,
                    )
                    if old_match.rated
                    else 0.0
                )
            else:
                change = (
                    rating_change(
                        winner_rating,
                        loser_rating,
                        old_match.multiplier,
                        old_match.k_factor,
                        old_match.elo_decimal_places,
                    )
                    if old_match.rated
                    else 0.0
                )
            winner_after = winner_rating + change
            loser_after = loser_rating - change
            if not math.isfinite(winner_after) or not math.isfinite(loser_after):
                raise ValueError("Resulting ratings must be finite.")
            rebuilt_matches.append(
                Match(
                    timestamp=old_match.timestamp,
                    winner_id=old_match.winner_id,
                    loser_id=old_match.loser_id,
                    loser_games=old_match.loser_games,
                    rating_change=change,
                    winner_rating_before=winner_rating,
                    loser_rating_before=loser_rating,
                    multiplier=old_match.multiplier,
                    winner_games=old_match.winner_games,
                    rated=old_match.rated,
                    k_factor=old_match.k_factor,
                    elo_decimal_places=old_match.elo_decimal_places,
                    is_draw=old_match.is_draw,
                )
            )
            replayed_ratings[old_match.winner_id] = winner_after
            replayed_ratings[old_match.loser_id] = loser_after
        self.players = retained_players
        for player in self.players:
            player.rating = replayed_ratings[player.id]
        self.matches = rebuilt_matches
        return {
            "added": [],
            "removed": [player.name for player in removed_players],
            "removed_match_count": removed_match_count,
        }

    def rename_player(self, player_id: int, new_name: str) -> None:
        cleaned_name = new_name.strip()
        if not cleaned_name:
            raise ValueError("Player name cannot be empty.")
        if len(cleaned_name) > 40:
            raise ValueError("Player name cannot be longer than 40 characters.")
        if any(
            player.id != player_id
            and player.name.casefold() == cleaned_name.casefold()
            for player in self.players
        ):
            raise ValueError("Player names must be unique.")
        self.player(player_id).name = cleaned_name

    def records(self) -> dict[int, tuple[int, int]]:
        return {
            player_id: (stats.matches_won, stats.matches_lost)
            for player_id, stats in self.statistics().items()
        }

    def head_to_head_percentages(
        self, player_ids: set[int]
    ) -> dict[int, float]:
        """Return match-score percentages within the selected player group."""
        points = {player_id: 0.0 for player_id in player_ids}
        matches_played = {player_id: 0 for player_id in player_ids}
        for match in self.matches:
            if (
                match.winner_id not in player_ids
                or match.loser_id not in player_ids
            ):
                continue
            matches_played[match.winner_id] += 1
            matches_played[match.loser_id] += 1
            if match.is_draw:
                points[match.winner_id] += 0.5
                points[match.loser_id] += 0.5
            else:
                points[match.winner_id] += 1.0
        return {
            player_id: (
                100.0 * points[player_id] / matches_played[player_id]
                if matches_played[player_id]
                else 0.0
            )
            for player_id in player_ids
        }

    def head_to_head_game_percentages(
        self, player_ids: set[int]
    ) -> dict[int, float]:
        """Return game-win percentages within the selected player group."""
        games_won = {player_id: 0 for player_id in player_ids}
        games_lost = {player_id: 0 for player_id in player_ids}
        for match in self.matches:
            if (
                match.is_draw
                or match.winner_id not in player_ids
                or match.loser_id not in player_ids
            ):
                continue
            games_won[match.winner_id] += match.winner_games
            games_lost[match.winner_id] += match.loser_games
            games_won[match.loser_id] += match.loser_games
            games_lost[match.loser_id] += match.winner_games
        return {
            player_id: (
                100.0
                * games_won[player_id]
                / (games_won[player_id] + games_lost[player_id])
                if games_won[player_id] + games_lost[player_id]
                else 0.0
            )
            for player_id in player_ids
        }

    def statistics(self) -> dict[int, PlayerStatistics]:
        """Return match and individual-game statistics for every player."""
        statistics = {
            player.id: PlayerStatistics() for player in self.players
        }
        for match in self.matches:
            winner = statistics[match.winner_id]
            loser = statistics[match.loser_id]
            if match.is_draw:
                winner.matches_drawn += 1
                loser.matches_drawn += 1
                continue
            winner.matches_won += 1
            loser.matches_lost += 1
            winner.games_won += match.winner_games
            winner.games_lost += match.loser_games
            loser.games_won += match.loser_games
            loser.games_lost += match.winner_games

        for match in self.matches:
            winner = statistics[match.winner_id]
            loser = statistics[match.loser_id]
            if match.is_draw:
                winner.sb_score += 0.5 * (
                    loser.matches_won + 0.5 * loser.matches_drawn
                )
                loser.sb_score += 0.5 * (
                    winner.matches_won + 0.5 * winner.matches_drawn
                )
            else:
                winner.sb_score += loser.matches_won + 0.5 * loser.matches_drawn

        return statistics

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEAGUE_SCHEMA_VERSION,
            "players": [asdict(player) for player in self.players],
            "matches": [asdict(match) for match in self.matches],
            "win_condition": asdict(self.win_condition),
            "calculate_elo": self.calculate_elo,
            "k_factor": self.k_factor,
            "elo_decimal_places": self.elo_decimal_places,
            "allow_draws": self.allow_draws,
            "base_elo": self.base_elo,
            "k_factor_scaling": self.k_factor_scaling,
            "tiebreaker_hierarchy": self.tiebreaker_hierarchy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "League":
        if not isinstance(data, dict):
            raise ValueError("The save file must contain a JSON object.")
        schema_version = data.get("schema_version")
        if schema_version not in (1, 2, 3, 4, 5, 6, 7, LEAGUE_SCHEMA_VERSION):
            raise ValueError("Unsupported save-file version.")

        try:
            win_cond_data = data.get("win_condition")
            if win_cond_data is not None:
                if not isinstance(win_cond_data, dict):
                    raise TypeError
                raw_multipliers = win_cond_data.get("score_multipliers", {})
                if not isinstance(raw_multipliers, dict):
                    raise TypeError
                mults = {
                    int(key): float(value)
                    for key, value in raw_multipliers.items()
                }
                win_condition = WinCondition(
                    games_to_win=win_cond_data.get("games_to_win", 3),
                    score_multipliers=mults,
                    score_mode=win_cond_data.get(
                        "score_mode", SCORE_MODE_FIXED
                    ),
                )
            else:
                win_condition = WinCondition()

            players = [Player(**item) for item in data["players"]]
            matches = []
            for item in data.get("matches", []):
                m_data = dict(item)
                if "multiplier" not in m_data:
                    m_data["multiplier"] = SCORE_MULTIPLIERS.get(m_data.get("loser_games", 0), 1.0)
                if "winner_games" not in m_data:
                    m_data["winner_games"] = 3
                if "rated" not in m_data:
                    m_data["rated"] = m_data.get("rating_change", 0.0) != 0.0
                if "k_factor" not in m_data:
                    m_data["k_factor"] = K_FACTOR
                if "elo_decimal_places" not in m_data:
                    m_data["elo_decimal_places"] = None
                if "is_draw" not in m_data:
                    m_data["is_draw"] = False
                matches.append(Match(**m_data))
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("The save file is malformed.") from error

        if schema_version == 1:
            if len(players) not in (LEGACY_PLAYER_COUNT, DEFAULT_PLAYER_COUNT):
                raise ValueError(
                    f"The legacy save file must contain {LEGACY_PLAYER_COUNT} or "
                    f"{DEFAULT_PLAYER_COUNT} players."
                )
        else:
            validate_player_count(len(players))
        if any(
            not isinstance(player.id, int)
            or isinstance(player.id, bool)
            or not isinstance(player.name, str)
            or not player.name.strip()
            for player in players
        ):
            raise ValueError("Every saved player must have a valid ID and name.")
        if len({player.id for player in players}) != len(players):
            raise ValueError("Player IDs in the save file must be unique.")
        if len({player.name.casefold() for player in players}) != len(players):
            raise ValueError("Player names in the save file must be unique.")
        if any(
            not isinstance(player.rating, (int, float))
            or isinstance(player.rating, bool)
            or not math.isfinite(player.rating)
            for player in players
        ):
            raise ValueError("Every saved rating must be a finite number.")

        # Preserve ratings and history from the original eight-player version.
        if schema_version == 1 and len(players) == LEGACY_PLAYER_COUNT:
            existing_names = {player.name.casefold() for player in players}
            next_id = max(player.id for player in players) + 1
            for player_number in range(
                LEGACY_PLAYER_COUNT + 1, DEFAULT_PLAYER_COUNT + 1
            ):
                name = f"Player {player_number}"
                while name.casefold() in existing_names:
                    name += " New"
                players.append(Player(id=next_id, name=name))
                existing_names.add(name.casefold())
                next_id += 1

        calculate_elo = data.get("calculate_elo", True)
        if not isinstance(calculate_elo, bool):
            raise ValueError("The auto-calculate Elo setting must be true or false.")
        try:
            k_factor = validate_k_factor(data.get("k_factor", K_FACTOR))
            elo_decimal_places = validate_elo_decimal_places(
                data.get(
                    "elo_decimal_places", DEFAULT_ELO_DECIMAL_PLACES
                )
            )
        except ValueError as error:
            raise ValueError("The save file has invalid Elo settings.") from error
        if elo_decimal_places is None:
            raise ValueError("The save file has invalid Elo settings.")
        allow_draws = data.get("allow_draws", True)
        if not isinstance(allow_draws, bool):
            raise ValueError("The allow-draws setting must be true or false.")
            
        try:
            base_elo = validate_base_elo(data.get("base_elo", INITIAL_RATING))
            k_factor_scaling = data.get("k_factor_scaling", False)
            if not isinstance(k_factor_scaling, bool):
                raise ValueError(
                    "The K-factor scaling setting must be true or false."
                )
            tiebreaker_hierarchy = validate_tiebreaker_hierarchy(
                data.get(
                    "tiebreaker_hierarchy",
                    list(DEFAULT_TIEBREAKER_HIERARCHY),
                )
            )
        except ValueError as error:
            raise ValueError("The save file has invalid league settings.") from error
            
        league = cls(
            players=players, 
            matches=matches, 
            win_condition=win_condition, 
            calculate_elo=calculate_elo,
            k_factor=k_factor,
            elo_decimal_places=elo_decimal_places,
            allow_draws=allow_draws,
            base_elo=base_elo,
            k_factor_scaling=k_factor_scaling,
            tiebreaker_hierarchy=tiebreaker_hierarchy,
        )
        valid_ids = {player.id for player in players}
        for match in matches:
            if (
                not isinstance(match.timestamp, str)
                or not isinstance(match.winner_id, int)
                or isinstance(match.winner_id, bool)
                or not isinstance(match.loser_id, int)
                or isinstance(match.loser_id, bool)
                or not isinstance(match.loser_games, int)
                or isinstance(match.loser_games, bool)
                or match.loser_games < 0
                or not isinstance(match.rating_change, (int, float))
                or isinstance(match.rating_change, bool)
                or not math.isfinite(match.rating_change)
                or (match.rating_change < 0 and not match.is_draw)
                or not isinstance(match.winner_rating_before, (int, float))
                or isinstance(match.winner_rating_before, bool)
                or not math.isfinite(match.winner_rating_before)
                or not isinstance(match.loser_rating_before, (int, float))
                or isinstance(match.loser_rating_before, bool)
                or not math.isfinite(match.loser_rating_before)
                or match.winner_id not in valid_ids
                or match.loser_id not in valid_ids
                or match.winner_id == match.loser_id
                or not isinstance(match.multiplier, (int, float))
                or isinstance(match.multiplier, bool)
                or not math.isfinite(match.multiplier)
                or match.multiplier < 0
                or not isinstance(match.winner_games, int)
                or isinstance(match.winner_games, bool)
                or match.winner_games < 0
                or match.winner_games > MAX_CUSTOM_SCORE
                or (
                    (match.winner_games != 0 or match.loser_games != 0)
                    if match.is_draw
                    else (match.winner_games <= 0 or match.loser_games >= match.winner_games)
                )
                or not isinstance(match.rated, bool)
                or not isinstance(match.k_factor, (int, float))
                or isinstance(match.k_factor, bool)
                or not math.isfinite(match.k_factor)
                or not MIN_K_FACTOR <= match.k_factor <= MAX_K_FACTOR
                or validate_elo_decimal_places(match.elo_decimal_places)
                != match.elo_decimal_places
                or not isinstance(match.is_draw, bool)
            ):
                raise ValueError("The save file contains an invalid match.")
            try:
                datetime.fromisoformat(match.timestamp)
            except ValueError as error:
                raise ValueError(
                    "The save file contains an invalid match."
                ) from error
        return league

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(self.to_dict(), indent=2, allow_nan=False), encoding="utf-8"
        )
        temporary_path.replace(path)

    @classmethod
    def load(cls, path: Path) -> "League":
        if not path.exists():
            return cls.new()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("The saved league data could not be read.") from error
        if not isinstance(data, dict):
            raise ValueError("The save file must contain a JSON object.")
        return cls.from_dict(data)


# Purpose: Core Elo rules, match validation, and league persistence.
# Upstream: UI and storage layers provide league configuration and saved JSON data.
# Upstream purpose: Collect user-entered results and restore persistent league state.
# Environment: Python 3.10+ on Windows, with platform-independent model tests.
# Generated: 2026-09-09 07:43 America/New_York.
# Changes: Validate and version configurable base Elo, K scaling, and tiebreaker
# settings; persist effective scaled multipliers; replay from saved initial ratings;
# reject unreadable UTF-8 saves; retain historical Elo and H2H behavior.
# Changed lines: 1-40 provenance/schema/defaults; 158-181 validators; 302-319
# initialization; 337-412 scaled transfers; 527-539 replay starting ratings;
# 730, 835-849, 932 schema migration, settings validation, and decode handling.
