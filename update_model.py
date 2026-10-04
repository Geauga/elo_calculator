import os

with open('elo_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "class WinCondition:\n    games_to_win": "class WinCondition:\n    \"\"\"Defines the scoring requirements for winning a match.\"\"\"\n    games_to_win",
    "class Player:\n    id": "class Player:\n    \"\"\"Represents a competitor with a rating and activity status.\"\"\"\n    id",
    "class Match:\n    timestamp": "class Match:\n    \"\"\"Records the outcome of a single match between two players.\"\"\"\n    timestamp",
    "class PlayerStatistics:\n    matches_won": "class PlayerStatistics:\n    \"\"\"Tracks the cumulative match and game records for a player.\"\"\"\n    matches_won",
    "class League:\n    players": "class League:\n    \"\"\"Manages the roster, settings, and full history of a league.\"\"\"\n    players"
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open('elo_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
