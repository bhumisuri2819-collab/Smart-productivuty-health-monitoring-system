"""
dashboard.py - Tkinter dashboard (dark mode) for live stats and exports.
Opens in a background thread while main.py runs the camera.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from analytics import generate_daily_report, load_today_data
from utils import format_duration, GRAPHS_DIR, REPORTS_DIR, DATA_DIR, open_folder
import alerts

DARK_BG = "#1e1e2e"
DARK_CARD = "#313244"
DARK_FG = "#cdd6f4"
ACCENT = "#89b4fa"
GREEN = "#a6e3a1"
RED = "#f38ba8"


class Dashboard:
    def __init__(self, stats_provider):
        self.stats_provider = stats_provider
        self.root = None
        self._thread = None
        self._labels = {}
        self._running = False
        self._sound_var = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.title("Smart Health Monitor — Dashboard")
        self.root.geometry("460x620")
        self.root.configure(bg=DARK_BG)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        ttk.Style().theme_use("clam")

        # Header
        header = tk.Frame(self.root, bg=DARK_BG)
        header.pack(fill="x", pady=(12, 8))
        tk.Label(header, text="Smart Productivity & Health", font=("Segoe UI", 15, "bold"),
                 bg=DARK_BG, fg=ACCENT).pack()
        tk.Label(header, text="Live session dashboard", font=("Segoe UI", 9),
                 bg=DARK_BG, fg="#6c7086").pack()

        # Stats card
        card = tk.Frame(self.root, bg=DARK_CARD, padx=12, pady=12)
        card.pack(fill="both", expand=True, padx=14, pady=6)

        fields = [
            ("daily_score", "Productivity Score"),
            ("fatigue_pct", "Fatigue Level"),
            ("drowsiness", "Drowsiness"),
            ("posture_score", "Posture Score"),
            ("posture_status", "Posture Status"),
            ("wellness", "Wellness Score"),
            ("blinks", "Blink Count"),
            ("focus_time", "Focus Time"),
            ("entertainment", "Entertainment Time"),
            ("session_time", "Session Time"),
            ("breaks", "Breaks Taken"),
            ("streak", "Day Streak"),
            ("emotion", "Mood / Focus"),
        ]
        for key, title in fields:
            row = tk.Frame(card, bg=DARK_CARD)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=title + ":", bg=DARK_CARD, fg=DARK_FG, width=20, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            val = tk.Label(row, text="--", bg=DARK_CARD, fg=GREEN, anchor="e", font=("Segoe UI", 10, "bold"))
            val.pack(side="right")
            self._labels[key] = val

        # Sound toggle
        opt = tk.Frame(self.root, bg=DARK_BG)
        opt.pack(pady=4)
        self._sound_var = tk.BooleanVar(value=alerts.SOUND_ENABLED)
        tk.Checkbutton(opt, text="Sound alerts", variable=self._sound_var,
                       command=self._toggle_sound, bg=DARK_BG, fg=DARK_FG,
                       selectcolor=DARK_CARD, activebackground=DARK_BG).pack()

        # Buttons row 1
        btn1 = tk.Frame(self.root, bg=DARK_BG)
        btn1.pack(pady=6)
        ttk.Button(btn1, text="Export Report (PDF+CSV)", command=self._export_report).pack(side="left", padx=3)
        ttk.Button(btn1, text="Refresh Stats", command=self._force_update).pack(side="left", padx=3)

        # Buttons row 2
        btn2 = tk.Frame(self.root, bg=DARK_BG)
        btn2.pack(pady=4)
        ttk.Button(btn2, text="Open Graphs", command=lambda: open_folder(GRAPHS_DIR)).pack(side="left", padx=3)
        ttk.Button(btn2, text="Open Reports", command=lambda: open_folder(REPORTS_DIR)).pack(side="left", padx=3)
        ttk.Button(btn2, text="Open Data (CSV)", command=lambda: open_folder(DATA_DIR)).pack(side="left", padx=3)

        tk.Label(self.root, text="Camera: Q=quit  |  B=log break", bg=DARK_BG, fg="#6c7086",
                 font=("Segoe UI", 9)).pack(pady=8)

        self._update_loop()
        self.root.mainloop()

    def _toggle_sound(self):
        alerts.set_sound_enabled(self._sound_var.get())

    def _force_update(self):
        self._update_labels()

    def _update_labels(self):
        try:
            s = self.stats_provider()
            self._labels["daily_score"].config(text=f"{s.get('productivity_score', 0):.0f} / 100")
            fatigue = s.get("fatigue_level", 0)
            self._labels["fatigue_pct"].config(text=f"{fatigue:.0f}%", fg=RED if fatigue > 50 else GREEN)
            self._labels["drowsiness"].config(text=f"{s.get('drowsiness_level', 0):.0f}%")
            self._labels["posture_score"].config(text=f"{s.get('posture_score', 0):.0f}")
            self._labels["posture_status"].config(text=str(s.get("posture_status", "--")))
            self._labels["wellness"].config(text=f"{s.get('wellness_score', 0):.0f}")
            self._labels["blinks"].config(text=str(s.get("blink_count", 0)))
            self._labels["focus_time"].config(text=format_duration(s.get("focus_seconds", 0)))
            self._labels["entertainment"].config(text=format_duration(s.get("entertainment_seconds", 0)))
            self._labels["session_time"].config(text=format_duration(s.get("session_seconds", 0)))
            self._labels["breaks"].config(text=str(s.get("break_count", 0)))
            self._labels["streak"].config(text=f"{s.get('streak_days', 1)} days")
            self._labels["emotion"].config(text=str(s.get("emotion", "Neutral")))
        except Exception:
            pass

    def _update_loop(self):
        if not self._running or self.root is None:
            return
        self._update_labels()
        self.root.after(1000, self._update_loop)

    def _export_report(self):
        try:
            s = self.stats_provider()
            result = generate_daily_report(s)
            n_graphs = len([g for g in result["graphs"] if "placeholder" not in str(g)])
            df = load_today_data()
            msg = (
                f"PDF report:\n{result['pdf']}\n\n"
                f"Summary CSV:\n{result['summary_csv']}\n\n"
                f"Graphs saved: {n_graphs}\n"
                f"Log rows today: {len(df)}"
            )
            messagebox.showinfo("Report Exported", msg)
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _on_close(self):
        self._running = False
        if self.root:
            self.root.destroy()
