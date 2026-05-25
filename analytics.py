"""
analytics.py - CSV logging, daily analytics, PNG graphs, PDF summary report.
"""

import csv
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from utils import DATA_DIR, GRAPHS_DIR, REPORTS_DIR, today_csv_path, format_duration

CSV_HEADERS = [
    "timestamp",
    "blink_count",
    "fatigue_level",
    "posture_status",
    "productivity_score",
    "focus_time_sec",
    "entertainment_time_sec",
    "break_count",
    "active_session_sec",
    "drowsiness_level",
    "posture_score",
    "wellness_score",
]


class AnalyticsLogger:
    """Writes periodic snapshots to data/log_YYYY-MM-DD.csv."""

    def __init__(self):
        self.break_count = 0
        self.rows_logged = 0
        self._ensure_header()

    def _ensure_header(self):
        path = today_csv_path()
        if not path.exists():
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(CSV_HEADERS)

    def log_row(self, stats: dict):
        path = today_csv_path()
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            stats.get("blink_count", 0),
            round(float(stats.get("fatigue_level", 0)), 1),
            stats.get("posture_status", ""),
            round(float(stats.get("productivity_score", 0)), 1),
            int(stats.get("focus_seconds", 0)),
            int(stats.get("entertainment_seconds", 0)),
            stats.get("break_count", self.break_count),
            int(stats.get("session_seconds", 0)),
            round(float(stats.get("drowsiness_level", 0)), 1),
            round(float(stats.get("posture_score", 0)), 1),
            round(float(stats.get("wellness_score", 0)), 1),
        ]
        try:
            with open(path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            self.rows_logged += 1
        except OSError as e:
            print(f"[Analytics] CSV write error: {e}")

    def increment_break(self):
        self.break_count += 1


def load_today_data():
    path = today_csv_path()
    if path.exists():
        try:
            df = pd.read_csv(path)
            if list(df.columns) == CSV_HEADERS or "timestamp" in df.columns:
                return df
        except Exception as e:
            print(f"[Analytics] Read error: {e}")
    return pd.DataFrame(columns=CSV_HEADERS)


def _save_fig(fig, path):
    path = Path(path)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_graphs(df, date_str=None):
    """Create all PNG charts in graphs/. Returns list of paths."""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)

    if df.empty or len(df) < 2:
        print("[Analytics] Need at least 2 log rows for graphs. Use the app a few minutes.")
        return _generate_demo_graphs(date_str)

    paths = []
    ts = pd.to_datetime(df["timestamp"], errors="coerce")

    # 1 Productivity
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(ts, df["productivity_score"], color="#2ecc71", linewidth=2, marker="o", markersize=3)
    ax.fill_between(ts, df["productivity_score"], alpha=0.15, color="#2ecc71")
    ax.set_title("Productivity Score Over Time", fontsize=12, weight="bold")
    ax.set_ylabel("Score (0-100)")
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    paths.append(_save_fig(fig, GRAPHS_DIR / f"productivity_{date_str}.png"))

    # 2 Eye fatigue
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(ts, df["fatigue_level"], color="#e74c3c", linewidth=2)
    ax.axhline(50, color="orange", linestyle="--", alpha=0.6, label="Moderate")
    ax.axhline(70, color="red", linestyle="--", alpha=0.6, label="High")
    ax.set_title("Eye Fatigue Report", fontsize=12, weight="bold")
    ax.set_ylabel("Fatigue %")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    paths.append(_save_fig(fig, GRAPHS_DIR / f"fatigue_{date_str}.png"))

    # 3 Posture score
    if "posture_score" in df.columns:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(ts, df["posture_score"], color="#9b59b6", linewidth=2)
        ax.set_title("Posture Improvement (Score Over Time)", fontsize=12, weight="bold")
        ax.set_ylabel("Posture Score")
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        paths.append(_save_fig(fig, GRAPHS_DIR / f"posture_{date_str}.png"))

    # 4 Screen time
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(ts, df["active_session_sec"] / 60, color="#3498db", linewidth=2)
    ax.set_title("Screen Time (Active Session Minutes)", fontsize=12, weight="bold")
    ax.set_ylabel("Minutes")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    paths.append(_save_fig(fig, GRAPHS_DIR / f"screentime_{date_str}.png"))

    # 5 Focus time trend
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(ts, df["focus_time_sec"] / 60, color="#1abc9c", linewidth=2)
    ax.set_title("Focus Time (Minutes)", fontsize=12, weight="bold")
    ax.set_ylabel("Minutes")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    paths.append(_save_fig(fig, GRAPHS_DIR / f"focus_{date_str}.png"))

    # 6 Pie: productive vs distraction
    last = df.iloc[-1]
    focus = float(last.get("focus_time_sec", 0))
    ent = float(last.get("entertainment_time_sec", 0))
    drowsy = float(last.get("drowsiness_level", 0))
    if focus + ent > 0:
        fig, ax = plt.subplots(figsize=(6, 6))
        sizes = [focus, ent]
        labels = ["Focus", "Entertainment"]
        if drowsy > 10:
            sizes.append(drowsy * 60)
            labels.append("Low attention")
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=["#2ecc71", "#e67e22", "#95a5a6"])
        ax.set_title("Productivity vs Distraction", fontsize=12, weight="bold")
        paths.append(_save_fig(fig, GRAPHS_DIR / f"pie_{date_str}.png"))

    # 7 Usage bar chart (summary stats)
    fig, ax = plt.subplots(figsize=(8, 4))
    metrics = {
        "Avg Productivity": df["productivity_score"].mean(),
        "Avg Fatigue": df["fatigue_level"].mean(),
        "Avg Posture": df["posture_score"].mean() if "posture_score" in df else 0,
        "Avg Wellness": df["wellness_score"].mean() if "wellness_score" in df else 0,
    }
    bars = ax.bar(metrics.keys(), metrics.values(), color=["#2ecc71", "#e74c3c", "#9b59b6", "#3498db"])
    ax.set_ylim(0, 100)
    ax.set_title("Daily Usage Statistics", fontsize=12, weight="bold")
    ax.set_ylabel("Average %")
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1, f"{b.get_height():.0f}", ha="center")
    plt.xticks(rotation=15)
    paths.append(_save_fig(fig, GRAPHS_DIR / f"usage_stats_{date_str}.png"))

    print(f"[Analytics] Saved {len(paths)} graphs to {GRAPHS_DIR}")
    return paths


def _generate_demo_graphs(date_str):
    """Placeholder charts when not enough session data yet."""
    paths = []
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, "Run the monitor longer to generate real graphs.\n(Need 2+ CSV log rows)",
            ha="center", va="center", fontsize=12)
    ax.axis("off")
    p = GRAPHS_DIR / f"placeholder_{date_str}.png"
    paths.append(_save_fig(fig, p))
    return paths


def generate_daily_report(stats: dict):
    """Export CSV summary + PNG graphs + PDF to reports/."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    df = load_today_data()
    graph_paths = generate_graphs(df, date_str)

    summary = {
        "date": date_str,
        "avg_productivity": round(df["productivity_score"].mean(), 1) if not df.empty else stats.get("productivity_score", 0),
        "avg_fatigue": round(df["fatigue_level"].mean(), 1) if not df.empty else stats.get("fatigue_level", 0),
        "avg_posture_score": round(df["posture_score"].mean(), 1) if not df.empty and "posture_score" in df else stats.get("posture_score", 0),
        "max_drowsiness": round(df["drowsiness_level"].max(), 1) if not df.empty and "drowsiness_level" in df else 0,
        "total_blinks": int(df["blink_count"].max()) if not df.empty else stats.get("blink_count", 0),
        "breaks": stats.get("break_count", 0),
        "log_rows": len(df),
        "focus_time": format_duration(stats.get("focus_seconds", 0)),
        "entertainment_time": format_duration(stats.get("entertainment_seconds", 0)),
        "session_time": format_duration(stats.get("session_seconds", 0)),
        "wellness_score": stats.get("wellness_score", 0),
        "posture_status": stats.get("posture_status", "Good"),
    }

    summary_path = REPORTS_DIR / f"daily_summary_{date_str}.csv"
    pd.DataFrame([summary]).to_csv(summary_path, index=False)

    pdf_path = REPORTS_DIR / f"daily_report_{date_str}.pdf"
    _build_pdf(pdf_path, summary, graph_paths, df)

    return {"summary_csv": summary_path, "pdf": pdf_path, "graphs": graph_paths, "summary": summary}


def _build_pdf(pdf_path, summary, graph_paths, df):
    try:
        with PdfPages(pdf_path) as pdf:
            fig = plt.figure(figsize=(8.5, 11))
            fig.text(0.5, 0.96, "Smart Health Monitor", ha="center", fontsize=18, weight="bold")
            fig.text(0.5, 0.92, "Daily Productivity & Wellness Report", ha="center", fontsize=12)

            y = 0.85
            sections = [
                ("Daily Summary", [
                    f"Date: {summary['date']}",
                    f"Average Productivity: {summary['avg_productivity']}%",
                    f"Average Fatigue: {summary['avg_fatigue']}%",
                    f"Average Posture Score: {summary['avg_posture_score']}%",
                    f"Peak Drowsiness: {summary.get('max_drowsiness', 0)}%",
                    f"Total Blinks: {summary['total_blinks']}",
                    f"Breaks Taken: {summary['breaks']}",
                    f"Data Points Logged: {summary.get('log_rows', 0)}",
                ]),
                ("Time Breakdown", [
                    f"Focus Time: {summary['focus_time']}",
                    f"Entertainment Time: {summary['entertainment_time']}",
                    f"Session Duration: {summary['session_time']}",
                    f"Wellness Score: {summary['wellness_score']}",
                    f"Last Posture: {summary.get('posture_status', 'N/A')}",
                ]),
                ("Recommendations", [
                    "- Take a 5-min break every 45 minutes of screen time.",
                    "- Blink often; look at something 20 feet away for 20 seconds.",
                    "- Keep shoulders level and screen at eye height.",
                    "- Drink water every 30 minutes.",
                ]),
            ]
            for title, lines in sections:
                fig.text(0.08, y, title, fontsize=13, weight="bold")
                y -= 0.035
                for line in lines:
                    fig.text(0.1, y, line, fontsize=10)
                    y -= 0.028
                y -= 0.02

            pdf.savefig(fig)
            plt.close(fig)

            for gp in graph_paths:
                gp = Path(gp)
                if gp.exists() and "placeholder" not in gp.name:
                    img = plt.imread(str(gp))
                    fig, ax = plt.subplots(figsize=(8.5, 5))
                    ax.imshow(img)
                    ax.axis("off")
                    pdf.savefig(fig)
                    plt.close(fig)

        print(f"[Analytics] PDF saved: {pdf_path}")
    except Exception as e:
        print(f"[Analytics] PDF error: {e}")
