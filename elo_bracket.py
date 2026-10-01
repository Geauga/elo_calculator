# elo_bracket.py
# Request: Add progressing single/double-elimination playoff brackets with byes.
"""Deterministic bracket routing, independent of GUI and Elo calculations."""

from dataclasses import dataclass


PLAYOFF_SINGLE = "single"
PLAYOFF_DOUBLE = "double"
PLAYOFF_FORMATS = {PLAYOFF_SINGLE: "Single elimination", PLAYOFF_DOUBLE: "Double elimination"}


@dataclass
class BracketMatch:
    id: str
    section: str
    round: int
    sources: tuple[tuple[str, int | str | None], tuple[str, int | str | None]]
    players: tuple[int | None, int | None] = (None, None)
    status: str = "pending"
    winner: int | None = None
    loser: int | None = None
    score: str = ""


@dataclass
class Bracket:
    matches: list[BracketMatch]
    champion: int | None = None

    @property
    def ready(self) -> list[BracketMatch]:
        return [match for match in self.matches if match.status == "ready"]


def _layout(seeds: list[int], format_name: str) -> list[BracketMatch]:
    if format_name not in PLAYOFF_FORMATS:
        raise ValueError("Unknown playoff format.")
    if not 2 <= len(seeds) <= 64 or len(set(seeds)) != len(seeds):
        raise ValueError("A bracket needs 2-64 unique entrants.")
    slots = 1 << (len(seeds) - 1).bit_length()
    order = [1, 2]
    while len(order) < slots:
        size = len(order) * 2
        order = [item for rank in order for item in (rank, size + 1 - rank)]
    nodes = []
    previous = []
    winners = []

    def add(section, round_number, sources):
        round_ids = []
        for index, pair in enumerate(sources, 1):
            key = f"{section}{round_number}-{index}"
            nodes.append(BracketMatch(key, section, round_number, pair))
            round_ids.append(key)
        return round_ids

    first = [("seed", seeds[rank - 1] if rank <= len(seeds) else None) for rank in order]
    previous = add("W", 1, list(zip(first[::2], first[1::2])))
    winners.append(previous)
    round_number = 1
    while len(previous) > 1:
        round_number += 1
        previous = add("W", round_number, [(("winner", a), ("winner", b))
                                           for a, b in zip(previous[::2], previous[1::2])])
        winners.append(previous)
    if format_name == PLAYOFF_SINGLE:
        return nodes
    if len(winners) == 1:
        lower_final = ("loser", winners[0][0])
    else:
        previous = add("L", 1, [(("loser", a), ("loser", b))
                                 for a, b in zip(winners[0][::2], winners[0][1::2])])
        for upper_round in range(2, len(winners) + 1):
            # Cross the incoming losers to avoid immediate first-round rematches.
            incoming = list(reversed(winners[upper_round - 1]))
            previous = add("L", 2 * upper_round - 2,
                           [(("winner", a), ("loser", b)) for a, b in zip(previous, incoming)])
            if upper_round < len(winners):
                previous = add("L", 2 * upper_round - 1,
                               [(("winner", a), ("winner", b))
                                for a, b in zip(previous[::2], previous[1::2])])
        lower_final = ("winner", previous[0])
    finalists = (("winner", winners[-1][0]), lower_final)
    add("F", 1, [finalists])
    add("F", 2, [finalists])
    return nodes


def build_bracket(seeds: list[int], format_name: str = PLAYOFF_SINGLE,
                  results: list[tuple[str, int, int, int, int]] | None = None) -> Bracket:
    """Replay ordered (match ID, winner, loser, winner score, loser score) results."""
    nodes = _layout(seeds, format_name)
    by_id = {node.id: node for node in nodes}
    saved = {}
    for index, (key, winner, loser, winner_score, loser_score) in enumerate(results or []):
        if key not in by_id or key in saved:
            raise ValueError("Unknown or duplicated bracket result.")
        saved[key] = (index, winner, loser, winner_score, loser_score)
    dependency_order = {}
    for node in nodes:
        resolved, latest = [], -1
        for kind, value in node.sources:
            if kind == "seed":
                resolved.append((True, value))
            else:
                source = by_id[value]
                latest = max(latest, dependency_order[value])
                done = source.status in ("complete", "bye")
                resolved.append((done, source.winner if kind == "winner" else source.loser))
        node.players = (resolved[0][1], resolved[1][1])
        if node.id == "F2-1":
            first_final = by_id["F1-1"]
            latest = max(latest, dependency_order["F1-1"])
            if first_final.status != "complete":
                resolved = [(False, None)]
            elif first_final.winner == first_final.players[0]:
                node.status = "not_needed"
        if node.status != "not_needed" and all(done for done, _ in resolved):
            if None in node.players:
                node.status = "bye"
                node.winner = next((p for p in node.players if p is not None), None)
            else:
                if node.players[0] == node.players[1]:
                    raise ValueError("A bracket match cannot contain the same player twice.")
                node.status = "ready"
        if node.id in saved:
            index, winner, loser, winner_score, loser_score = saved[node.id]
            if node.status != "ready" or index <= latest:
                raise ValueError("Bracket result was recorded before its match was ready.")
            if {winner, loser} != set(node.players) or winner == loser:
                raise ValueError("Saved bracket result does not match its scheduled players.")
            if (not isinstance(winner_score, int) or isinstance(winner_score, bool)
                    or not isinstance(loser_score, int) or isinstance(loser_score, bool)
                    or not 0 <= loser_score < winner_score):
                raise ValueError("A bracket result requires a decisive whole-number score.")
            node.status, node.winner, node.loser = "complete", winner, loser
            node.score = f"{winner_score}-{loser_score}"
            latest = index
        dependency_order[node.id] = latest
    if format_name == PLAYOFF_SINGLE:
        final = nodes[-1]
        champion = final.winner if final.status in ("complete", "bye") else None
    else:
        first_final, reset = by_id["F1-1"], by_id["F2-1"]
        champion = (reset.winner if reset.status == "complete" else
                    first_final.winner if reset.status == "not_needed" else None)
    return Bracket(nodes, champion)


# Purpose: Route winners/losers, automatic byes and the conditional grand-final reset.
# Upstream: elo_model.py supplies frozen seeds and saved playoff results; the GUI
# displays the returned graph and records ready matches. Python 3.12 / Windows Tk.
# Generated: 2026-10-01 America/New_York. Changes: New bracket engine.
