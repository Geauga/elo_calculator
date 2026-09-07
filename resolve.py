with open("elo_calculator.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
in_conflict = False
conflict_part = 0 # 1 = HEAD, 2 = Incoming
head_lines = []
incoming_lines = []

for line in lines:
    if line.startswith("<<<<<<< HEAD"):
        in_conflict = True
        conflict_part = 1
        head_lines = []
        incoming_lines = []
    elif line.startswith("======="):
        conflict_part = 2
    elif line.startswith(">>>>>>> de142aa"):
        in_conflict = False
        conflict_part = 0
        
        # Resolve logic: we want the Draw logic (result, elo_change) but with formatting if it exists.
        # Let's inspect the context.
        # If it's the history log insertion:
        if any("winner_games" in l for l in head_lines) and any("result" in l for l in incoming_lines):
            # It seems the draw commit added `result` and `elo_change` before this block.
            # We should just use result and elo_change.
            # But wait, looking at the diff, incoming (de142aa) had `result, elo_change`?
            # Let's just use result and elo_change.
            new_lines.extend(incoming_lines)
        elif any("Undo " in l for l in head_lines):
            # Undo confirmation
            new_lines.extend(incoming_lines)
        elif any("Generated:" in l for l in head_lines):
            # Header changes
            new_lines.extend(head_lines)
            new_lines.extend(incoming_lines)
        else:
            # fallback: use incoming
            new_lines.extend(incoming_lines)
    else:
        if conflict_part == 1:
            head_lines.append(line)
        elif conflict_part == 2:
            incoming_lines.append(line)
        else:
            new_lines.append(line)

with open("elo_calculator.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
