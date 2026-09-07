    def _build_graphs_tab(self, parent) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(controls, text="Player:").pack(side="left")
        self.graph_player_combo = ttk.Combobox(
            controls, state="readonly", width=15
        )
        self.graph_player_combo.pack(side="left", padx=(4, 16))
        self.graph_player_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_graph())
        self.graph_metric_var = tk.StringVar(value="elo")
        for metric, label in (("elo", "Elo"), ("pct", "Win %"), ("sb", "SB Score")):
            rb = ttk.Radiobutton(
                controls,
                text=label,
                value=metric,
                variable=self.graph_metric_var,
                command=self._refresh_graph,
            )
            rb.pack(side="left", padx=4)
        self.graph_canvas = tk.Canvas(parent, bg="white", highlightthickness=1, highlightbackground="#cccccc")
        self.graph_canvas.grid(row=1, column=0, sticky="nsew")
        self.graph_canvas.bind("<Configure>", lambda e: self._refresh_graph())

    def _refresh_graph(self) -> None:
        if not hasattr(self, "graph_canvas"): return
        self.graph_canvas.delete("all")
        width = self.graph_canvas.winfo_width()
        height = self.graph_canvas.winfo_height()
        if width < 50 or height < 50: return

        player_name = self.graph_player_combo.get()
        player_id = self.player_name_to_id.get(player_name)
        if player_id is None: return

        metric = self.graph_metric_var.get()
        matches = self.league.matches
        
        y_values = []
        if metric == "elo":
            current_elo = 1500.0
            y_values.append(current_elo)
            for m in matches:
                if m.winner_id == player_id:
                    current_elo += m.rating_change
                    y_values.append(current_elo)
                elif m.loser_id == player_id:
                    current_elo -= m.rating_change
                    y_values.append(current_elo)
        elif metric == "pct":
            wins = 0
            total = 0
            y_values.append(0.0)
            for m in matches:
                if m.winner_id == player_id or m.loser_id == player_id:
                    total += 1
                    if m.winner_id == player_id:
                        wins += 1
                    y_values.append((wins / total) * 100)
        elif metric == "sb":
            mw = {p.id: 0 for p in self.league.players}
            defeated = []
            y_values.append(0.0)
            for m in matches:
                mw[m.winner_id] += 1
                if m.winner_id == player_id:
                    defeated.append(m.loser_id)
                if m.winner_id == player_id or m.loser_id == player_id:
                    sb = sum(mw[opp_id] for opp_id in defeated)
                    y_values.append(sb)

        if not y_values:
            return

        min_y = min(y_values)
        max_y = max(y_values)
        if min_y == max_y:
            min_y -= 1
            max_y += 1
            
        margin_x = 45
        margin_y = 20
        
        self.graph_canvas.create_line(margin_x, height - margin_y, width, height - margin_y, fill="#cccccc")
        self.graph_canvas.create_line(margin_x, 0, margin_x, height - margin_y, fill="#cccccc")
        
        for i in range(5):
            y_pos = margin_y + i * (height - 2 * margin_y) / 4
            val = max_y - i * (max_y - min_y) / 4
            self.graph_canvas.create_line(margin_x, y_pos, width, y_pos, fill="#eeeeee", dash=(4, 4))
            self.graph_canvas.create_text(margin_x - 5, y_pos, text=f"{val:.1f}", anchor="e", font=("Segoe UI", 8), fill="#666666")
            
        if len(y_values) == 1:
            x = margin_x + (width - margin_x) / 2
            y = margin_y + (max_y - y_values[0]) / (max_y - min_y) * (height - 2 * margin_y)
            self.graph_canvas.create_oval(x-3, y-3, x+3, y+3, fill="#0078D7", outline="#0078D7")
        else:
            points = []
            for i, val in enumerate(y_values):
                x = margin_x + (i / (len(y_values) - 1)) * (width - margin_x - 10)
                y = margin_y + (max_y - val) / (max_y - min_y) * (height - 2 * margin_y)
                points.extend([x, y])
            self.graph_canvas.create_line(points, fill="#0078D7", width=2)
