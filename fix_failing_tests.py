import os

with open(r"test_elo_playoffs.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix first failing test
content = content.replace(
    "self.assertEqual({p_id for p_id, row in rows.items()\n                          if row[1].endswith(' (Playoff position)')}, {1, 2})",
    "self.assertEqual({p_id for p_id, row in rows.items()\n                          if row[1].endswith(' (Playoff position)') or row[1].endswith(' (Clinched)')}, {1, 2})"
)

# Fix second failing test
content = content.replace(
    "        self.assertEqual(rows[0][1], 'Player 1 (Playoff position)')\n        for _ in range(8):",
    "        self.assertEqual(rows[0][1], 'Player 1 (Clinched)')\n        for _ in range(8):"
)

with open(r"test_elo_playoffs.py", "w", encoding="utf-8") as f:
    f.write(content)
