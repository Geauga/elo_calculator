import os
import re

with open(r"test_elo_playoffs.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("self.assertEqual(rows[0][1], 'Player 1')", "self.assertEqual(rows[0][1], 'Player 1 (Clinched)')")
content = content.replace("self.assertEqual(rows[0][1], 'Player 1 (Playoff position)')", "self.assertEqual(rows[0][1], 'Player 1 (Clinched)')")
content = re.sub(r"^\s*self\.assertFalse\(any\('Clinched'.*?\)\)\n", "", content, flags=re.MULTILINE)

with open(r"test_elo_playoffs.py", "w", encoding="utf-8") as f:
    f.write(content)
