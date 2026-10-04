import os

with open(r"elo_calculator.py", "r", encoding="utf-8") as f:
    content = f.read()

# Make Clinched only apply if they are actually in qualifier_ids
content = content.replace("if player.id in clinched_ids:", "if player.id in clinched_ids and player.id in qualifier_ids:")

with open(r"elo_calculator.py", "w", encoding="utf-8") as f:
    f.write(content)
