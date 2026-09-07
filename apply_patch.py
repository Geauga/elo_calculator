with open("elo_calculator.py", "r", encoding="utf-8") as f:
    code = f.read()

with open("graph_patch.py", "r", encoding="utf-8") as f:
    patch = f.read()

code = code.replace("    def _apply_theme(self", patch + "\n    def _apply_theme(self")

refresh_block = """        if hasattr(self, "graph_player_combo"):
            self.graph_player_combo["values"] = names
            if self.graph_player_combo.get() not in names and names:
                self.graph_player_combo.set(names[0])
            self._refresh_graph()

        self._update_preview()"""

code = code.replace("        self._update_preview()", refresh_block)

with open("elo_calculator.py", "w", encoding="utf-8") as f:
    f.write(code)
