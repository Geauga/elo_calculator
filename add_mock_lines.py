import os

with open("elo_calculator.py", 'r', encoding='utf-8') as f:
    content = f.read()

# Helper function to add
helper = """def american_odds(probability: float) -> str:
    if probability <= 0.0 or probability >= 1.0:
        return "N/A"
    if probability > 0.5:
        return str(int(-100 * probability / (1 - probability)))
    else:
        return f"+{int(100 * (1 - probability) / probability)}"

class EloCalculatorApp:"""

content = content.replace("class EloCalculatorApp:", helper)

old_preview = """        preview_text = (
            f"Margin multiplier: {preview['multiplier']:.0%}\\n"
            f"Expected chance: {winner.name} {preview['winner_expected']:.1%}, "
            f"{loser.name} {preview['loser_expected']:.1%}\\n"
            f"Change: +/-{self._format_elo(preview['change'])} Elo\\n""""

new_preview = """        preview_text = (
            f"Margin multiplier: {preview['multiplier']:.0%}\\n"
            f"Expected chance: {winner.name} {preview['winner_expected']:.1%} ({american_odds(preview['winner_expected'])}), "
            f"{loser.name} {preview['loser_expected']:.1%} ({american_odds(preview['loser_expected'])})\\n"
            f"Change: +/-{self._format_elo(preview['change'])} Elo\\n""""

content = content.replace(old_preview, new_preview)

with open("elo_calculator.py", 'w', encoding='utf-8') as f:
    f.write(content)
