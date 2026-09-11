# elo_storage.py
# Request: Persist explicit SB scores for match-related activity entries.
"""Multiple-league persistence, backups, and append-only audit logging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from elo_model import DEFAULT_PLAYER_COUNT, League


COLLECTION_SCHEMA_VERSION = 2
MAX_LEAGUES = 100
MAX_BACKUPS = 50


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary_path.replace(path)


def _read_tail_utf8_lines(path: Path, limit: int) -> list[str]:
    """Read at most the final JSONL records without loading an unbounded log."""
    if limit <= 0:
        return []
    block_size = 8192
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        position = file.tell()
        buffer = b""
        while position > 0 and buffer.count(b"\n") <= limit:
            read_size = min(block_size, position)
            position -= read_size
            file.seek(position)
            buffer = file.read(read_size) + buffer
    lines: list[str] = []
    for raw_line in buffer.splitlines()[-limit:]:
        try:
            lines.append(raw_line.decode("utf-8"))
        except UnicodeError:
            continue
    return lines


def validate_league_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("League name must be text.")
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("League name cannot be empty.")
    if len(cleaned) > 50:
        raise ValueError("League name cannot be longer than 50 characters.")
    return cleaned


@dataclass
class NamedLeague:
    id: str
    name: str
    created_at: str
    league: League

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "league": self.league.to_dict(),
        }


@dataclass
class LeagueCollection:
    leagues: list[NamedLeague]
    active_league_id: str
    migrated_from_single_league: bool = False

    @classmethod
    def new(cls) -> "LeagueCollection":
        league_id = str(uuid4())
        return cls(
            leagues=[
                NamedLeague(
                    id=league_id,
                    name="League 1",
                    created_at=now_iso(),
                    league=League.new(),
                )
            ],
            active_league_id=league_id,
        )

    @property
    def active(self) -> NamedLeague:
        return self.by_id(self.active_league_id)

    def by_id(self, league_id: str) -> NamedLeague:
        for named_league in self.leagues:
            if named_league.id == league_id:
                return named_league
        raise ValueError(f"Unknown league ID: {league_id}")

    def create_league(
        self, name: str, player_count: int = DEFAULT_PLAYER_COUNT
    ) -> NamedLeague:
        cleaned = validate_league_name(name)
        self._ensure_unique_name(cleaned)
        if len(self.leagues) >= MAX_LEAGUES:
            raise ValueError(f"No more than {MAX_LEAGUES} leagues are supported.")
        named_league = NamedLeague(
            id=str(uuid4()),
            name=cleaned,
            created_at=now_iso(),
            league=League.new(player_count),
        )
        self.leagues.append(named_league)
        self.active_league_id = named_league.id
        return named_league

    def rename_league(self, league_id: str, name: str) -> tuple[str, str]:
        named_league = self.by_id(league_id)
        cleaned = validate_league_name(name)
        self._ensure_unique_name(cleaned, exclude_id=league_id)
        old_name = named_league.name
        named_league.name = cleaned
        return old_name, cleaned

    def delete_league(self, league_id: str) -> NamedLeague:
        if len(self.leagues) == 1:
            raise ValueError("The only league cannot be deleted.")
        named_league = self.by_id(league_id)
        self.leagues.remove(named_league)
        if self.active_league_id == league_id:
            self.active_league_id = self.leagues[0].id
        return named_league

    def switch_to(self, league_id: str) -> None:
        self.by_id(league_id)
        self.active_league_id = league_id

    def _ensure_unique_name(self, name: str, exclude_id: str | None = None) -> None:
        if any(
            item.id != exclude_id and item.name.casefold() == name.casefold()
            for item in self.leagues
        ):
            raise ValueError("League names must be unique.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COLLECTION_SCHEMA_VERSION,
            "active_league_id": self.active_league_id,
            "leagues": [item.to_dict() for item in self.leagues],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeagueCollection":
        if not isinstance(data, dict):
            raise ValueError("The league database must contain a JSON object.")
        schema_version = data.get("schema_version")
        if schema_version == 1:
            # Upgrade the original single-league file without losing any data.
            league_id = str(uuid4())
            return cls(
                leagues=[
                    NamedLeague(
                        id=league_id,
                        name="League 1",
                        created_at=now_iso(),
                        league=League.from_dict(data),
                    )
                ],
                active_league_id=league_id,
                migrated_from_single_league=True,
            )
        if schema_version != COLLECTION_SCHEMA_VERSION:
            raise ValueError("Unsupported league database version.")

        raw_leagues = data.get("leagues")
        if not isinstance(raw_leagues, list) or not raw_leagues:
            raise ValueError("The league database must contain at least one league.")
        if len(raw_leagues) > MAX_LEAGUES:
            raise ValueError(f"The league database exceeds {MAX_LEAGUES} leagues.")

        leagues: list[NamedLeague] = []
        try:
            for item in raw_leagues:
                league_id = item["id"]
                name = validate_league_name(item["name"])
                created_at = item["created_at"]
                if not isinstance(league_id, str) or not league_id:
                    raise ValueError("Every league must have a valid ID.")
                if not isinstance(created_at, str) or not created_at:
                    raise ValueError("Every league must have a creation date.")
                leagues.append(
                    NamedLeague(
                        id=league_id,
                        name=name,
                        created_at=created_at,
                        league=League.from_dict(item["league"]),
                    )
                )
        except (KeyError, TypeError) as error:
            raise ValueError("The league database is malformed.") from error

        ids = {item.id for item in leagues}
        names = {item.name.casefold() for item in leagues}
        if len(ids) != len(leagues):
            raise ValueError("League IDs must be unique.")
        if len(names) != len(leagues):
            raise ValueError("League names must be unique.")
        active_id = data.get("active_league_id")
        if not isinstance(active_id, str) or active_id not in ids:
            raise ValueError("The active league does not exist.")
        return cls(leagues=leagues, active_league_id=active_id)

    def save(self, path: Path) -> None:
        _atomic_json_write(path, self.to_dict())

    @classmethod
    def load(cls, path: Path) -> "LeagueCollection":
        if not path.exists():
            return cls.new()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("The saved league database could not be read.") from error
        if not isinstance(data, dict):
            raise ValueError("The league database must contain a JSON object.")
        return cls.from_dict(data)


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: str
    reason: str


class BackupManager:
    def __init__(self, directory: Path, max_backups: int = MAX_BACKUPS) -> None:
        if (
            not isinstance(max_backups, int)
            or isinstance(max_backups, bool)
            or max_backups < 1
        ):
            raise ValueError("At least one backup must be retained.")
        self.directory = directory
        self.max_backups = max_backups

    def create(
        self,
        collection: LeagueCollection,
        reason: str,
        protected_paths: tuple[Path, ...] = (),
    ) -> BackupInfo:
        self.directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone()
        safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "-", reason).strip("-")[:40]
        safe_reason = safe_reason or "backup"
        filename = f"{timestamp.strftime('%Y%m%d-%H%M%S-%f')}_{safe_reason}.json"
        path = self.directory / filename
        payload = {
            "backup_schema_version": 1,
            "created_at": timestamp.isoformat(timespec="seconds"),
            "reason": reason,
            "database": collection.to_dict(),
        }
        _atomic_json_write(path, payload)
        self._prune((path, *protected_paths))
        if not path.exists():
            raise OSError("The newly created backup was not retained.")
        return BackupInfo(path=path, created_at=payload["created_at"], reason=reason)

    def list(self) -> list[BackupInfo]:
        if not self.directory.exists():
            return []
        backups: list[BackupInfo] = []
        for path in sorted(self.directory.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if (
                    not isinstance(data, dict)
                    or data.get("backup_schema_version") != 1
                ):
                    continue
                backups.append(
                    BackupInfo(
                        path=path,
                        created_at=str(data["created_at"]),
                        reason=str(data["reason"]),
                    )
                )
            except (
                OSError,
                UnicodeError,
                KeyError,
                json.JSONDecodeError,
                TypeError,
            ):
                continue
        return backups

    def restore(self, backup: BackupInfo) -> LeagueCollection:
        resolved_directory = self.directory.resolve()
        resolved_path = backup.path.resolve()
        if resolved_path.parent != resolved_directory:
            raise ValueError("The selected backup is outside the backup directory.")
        try:
            data = json.loads(resolved_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("The backup could not be read.") from error
        if not isinstance(data, dict):
            raise ValueError("The backup is malformed.")
        if data.get("backup_schema_version") != 1:
            raise ValueError("Unsupported backup version.")
        database = data.get("database")
        if not isinstance(database, dict):
            raise ValueError("The backup is malformed.")
        return LeagueCollection.from_dict(database)

    def _prune(self, protected_paths: tuple[Path, ...] = ()) -> None:
        paths = sorted(self.directory.glob("*.json"), reverse=True)
        protected = {path.resolve() for path in protected_paths}
        existing_protected = {
            path.resolve() for path in paths if path.resolve() in protected
        }
        keep = set(existing_protected)
        for path in paths:
            resolved = path.resolve()
            if resolved in keep:
                continue
            if len(keep) < self.max_backups:
                keep.add(resolved)
        for old_path in paths:
            if old_path.resolve() not in keep:
                old_path.unlink(missing_ok=True)


class AuditLog:
    """Append-only JSON Lines activity log, independent of league snapshots."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(
        self,
        action: str,
        league_id: str | None,
        league_name: str | None,
        details: str,
        sb_scores: str = "",
    ) -> dict[str, Any]:
        entry = {
            "timestamp": now_iso(),
            "action": action,
            "league_id": league_id,
            "league_name": league_name,
            "details": details,
            "sb_scores": sb_scores,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        return entry

    def read(self, limit: int = 500) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = _read_tail_utf8_lines(self.path, limit)
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries


# Purpose: Multiple-league persistence, backups, and append-only audit logging.
# Upstream: elo_model.py supplies validated league state and serialization.
# Upstream purpose: Model league rules, matches, ratings, and migrations.
# Environment: Python 3.10+ on Windows with platform-independent storage tests.
# Generated: 2026-09-10 20:19 America/New_York.
# Changes: Treat invalid UTF-8 as malformed auxiliary data, bound audit-log reads,
# protect newly created/selected recovery snapshots during pruning, and retain
# the public collection-validation contracts.
# Changed lines: 1-2 provenance; 37-59 tail reader; 240, 308-325 decode handling;
# 256-286 retention validation/protected snapshots; 336-351 pruning;
# 360-380 optional structured SB-score audit field; 387-391 bounded audit reading.
