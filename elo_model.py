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
LEAGUE_SCHEMA_VERSION = 4
INITIAL_RATING = 1500.0
K_FACTOR = 32.0
SCORE_MULTIPLIERS = {0: 1.0, 1: 0.75, 2: 0.50}
MAX_GAMES_TO_WIN = 100


@dataclass
class WinCondition:
    games_to_win: int = 3
    score_multipliers: dict[int, float] = field(default_factory=lambda: {0: 1.0, 1: 0.75, 2: 0.50})

    def __post_init__(self) -> None:
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

    def get_multiplier(self, loser_games: int) -> float:
        if not isinstance(loser_games, int) or isinstance(loser_games, bool) or loser_games < 0 or loser_games >= self.games_to_win:
            raise ValueError(f"Loser games must be between 0 and {self.games_to_win - 1}.")
        return self.score_multipliers.get(loser_games, 1.0)


def validate_player_count(player_count: int) -> int:
    if not isinstance(player_count, int) or isinstance(player_count, bool):
        raise ValueError("Player count must be a whole number.")
    if not MIN_PLAYER_COUNT <= player_count <= MAX_PLAYER_COUNT:
        raise ValueError(
            f"Player count must be between {MIN_PLAYER_COUNT} and "
            f"{MAX_PLAYER_COUNT}."
        )
    return player_count


def expected_score(rating: float, opponent_rating: float) -> float:
    """Return the standard Elo expected score for one player."""
    exponent = max(-10.0, min(10.0, (opponent_rating - rating) / 400.0))
    return 1.0 / (1.0 + (10.0**exponent))


def rating_change(
    winner_rating: float,
    loser_rating: float,
    multiplier: float = 1.0,
) -> float:
    """Return the Elo transferred."""
    if (
        not isinstance(multiplier, (int, float))
        or isinstance(multiplier, bool)
        or not math.isfinite(multiplier)
        or multiplier < 0
    ):
        raise ValueError("Multiplier must be a finite, nonnegative number.")

    return K_FACTOR * multiplier * (
        1.0 - expected_score(winner_rating, loser_rating)
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


@dataclass
class PlayerStatistics:
    matches_won: int = 0
    matches_lost: int = 0
    games_won: int = 0
    games_lost: int = 0

    @property
    def match_win_percentage(self) -> float:
        total = self.matches_won + self.matches_lost
        return 100.0 * self.matches_won / total if total else 0.0

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

    def preview_match(
        self, winner_id: int, loser_id: int, loser_games: int
    ) -> dict[str, float]:
        if winner_id == loser_id:
            raise ValueError("Winner and loser must be different players.")

        winner = self.player(winner_id)
        loser = self.player(loser_id)
        multiplier = self.win_condition.get_multiplier(loser_games)
        change = rating_change(winner.rating, loser.rating, multiplier) if self.calculate_elo else 0.0
        return {
            "winner_expected": expected_score(winner.rating, loser.rating),
            "loser_expected": expected_score(loser.rating, winner.rating),
            "multiplier": multiplier,
            "change": change,
            "winner_after": winner.rating + change,
            "loser_after": loser.rating - change,
        }

    def record_match(
        self, winner_id: int, loser_id: int, loser_games: int
    ) -> Match:
        preview = self.preview_match(winner_id, loser_id, loser_games)
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
            multiplier=preview["multiplier"],
            winner_games=self.win_condition.games_to_win,
            rated=self.calculate_elo,
        )
        winner.rating = preview["winner_after"]
        loser.rating = preview["loser_after"]
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
            player.rating = INITIAL_RATING
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
                self.players.append(Player(id=next_id, name=name))
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
        self.players = self.players[:player_count]

        # Dropping a match changes the inputs to later Elo calculations. Replay
        # retained results in their original order so the remaining standings
        # are mathematically consistent rather than carrying ghost Elo.
        for player in self.players:
            player.rating = INITIAL_RATING
        rebuilt_matches: list[Match] = []
        for old_match in retained_matches:
            winner = self.player(old_match.winner_id)
            loser = self.player(old_match.loser_id)
            change = (
                rating_change(winner.rating, loser.rating, old_match.multiplier)
                if old_match.rated
                else 0.0
            )
            rebuilt_matches.append(
                Match(
                    timestamp=old_match.timestamp,
                    winner_id=old_match.winner_id,
                    loser_id=old_match.loser_id,
                    loser_games=old_match.loser_games,
                    rating_change=change,
                    winner_rating_before=winner.rating,
                    loser_rating_before=loser.rating,
                    multiplier=old_match.multiplier,
                    winner_games=old_match.winner_games,
                    rated=old_match.rated,
                )
            )
            winner.rating += change
            loser.rating -= change
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

    def statistics(self) -> dict[int, PlayerStatistics]:
        """Return match and individual-game statistics for every player."""
        statistics = {
            player.id: PlayerStatistics() for player in self.players
        }
        for match in self.matches:
            winner = statistics[match.winner_id]
            loser = statistics[match.loser_id]
            winner.matches_won += 1
            loser.matches_lost += 1
            winner.games_won += match.winner_games
            winner.games_lost += match.loser_games
            loser.games_won += match.loser_games
            loser.games_lost += match.winner_games
        return statistics

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEAGUE_SCHEMA_VERSION,
            "players": [asdict(player) for player in self.players],
            "matches": [asdict(match) for match in self.matches],
            "win_condition": asdict(self.win_condition),
            "calculate_elo": self.calculate_elo,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "League":
        if not isinstance(data, dict):
            raise ValueError("The save file must contain a JSON object.")
        schema_version = data.get("schema_version")
        if schema_version not in (1, 2, 3, LEAGUE_SCHEMA_VERSION):
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
        league = cls(
            players=players, 
            matches=matches, 
            win_condition=win_condition, 
            calculate_elo=calculate_elo
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
                or match.rating_change < 0
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
                or match.winner_games <= 0
                or match.loser_games >= match.winner_games
                or not isinstance(match.rated, bool)
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
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("The saved league data could not be read.") from error
        if not isinstance(data, dict):
            raise ValueError("The save file must contain a JSON object.")
        return cls.from_dict(data)
