"""Fishing calibration — records hold time vs bobber landing position."""

import csv
import tkinter as tk
from tkinter import ttk, filedialog
import time
from enum import Enum, auto

try:
    from pynput import mouse as _mouse_lib
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynput"])
    from pynput import mouse as _mouse_lib

BG   = "#1a1a2e"
CARD = "#16213e"
ACC  = "#0f3460"
HOT  = "#e94560"
FG   = "#eaeaea"
MONO = ("Consolas", 10)


class State(Enum):
    IDLE           = auto()
    CASTING        = auto()
    WAITING_BOBBER = auto()


class CalibrationApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Fishing Calibration")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.left_bound:  int | None = None
        self.right_bound: int | None = None
        self.state       = State.IDLE
        self.cast_start  = 0.0
        self.data: list[tuple[float, float, int]] = []   # (hold_ms, position, raw_x)
        self.monitoring  = False
        self._picking    = False   # suppresses mouse listener during bound pick

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        PAD = 16

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background=ACC, foreground=FG, borderwidth=0,
                        focusthickness=0, font=("Segoe UI", 10, "bold"), padding=6)
        style.map("TButton", background=[("active", HOT)])

        tk.Label(self, text="Fishing Calibration",
                 font=("Segoe UI", 14, "bold"), bg=BG, fg=HOT).pack(pady=(PAD, 4), padx=PAD)
        tk.Label(self, text="Hold left-click to cast, then click where the bobber lands",
                 font=("Segoe UI", 9), bg=BG, fg="#888").pack(padx=PAD, pady=(0, PAD))

        # ── Bounds card ───────────────────────────────────────────────────────
        bounds_card = tk.Frame(self, bg=CARD, padx=12, pady=10,
                               highlightbackground=ACC, highlightthickness=1)
        bounds_card.pack(padx=PAD, fill="x")

        tk.Label(bounds_card, text="Fishing Zone Bounds",
                 font=("Segoe UI", 10, "bold"), bg=CARD, fg=FG).pack(anchor="w", pady=(0, 6))

        for side, attr in (("Left", "left"), ("Right", "right")):
            row = tk.Frame(bounds_card, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{side} Bound:", font=("Segoe UI", 9),
                     bg=CARD, fg="#aaa", width=12, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="Not set", font=MONO, bg=CARD, fg="#aaa")
            lbl.pack(side="left", padx=(4, 8))
            setattr(self, f"{attr}_lbl", lbl)
            ttk.Button(row, text=f"Pick {side}",
                       command=lambda a=attr: self._pick_bound(a)).pack(side="right")

        # ── Data table ────────────────────────────────────────────────────────
        table_card = tk.Frame(self, bg=CARD, padx=12, pady=10,
                              highlightbackground=ACC, highlightthickness=1)
        table_card.pack(padx=PAD, pady=(PAD, 0), fill="x")

        tk.Label(table_card, text="Recorded Casts",
                 font=("Segoe UI", 10, "bold"), bg=CARD, fg=FG).pack(anchor="w", pady=(0, 4))

        hdr = tk.Frame(table_card, bg=CARD)
        hdr.pack(fill="x")
        for col, w in (("Hold (ms)", 12), ("Position", 10), ("Rel X", 8)):
            tk.Label(hdr, text=col, font=("Segoe UI", 8, "bold"),
                     bg=CARD, fg="#aaa", width=w, anchor="w").pack(side="left")

        self.table = tk.Text(table_card, font=MONO, bg="#0d1730", fg=FG,
                             height=8, width=38, relief="flat",
                             state="disabled", cursor="arrow")
        self.table.pack(fill="x", pady=(2, 0))

        # ── Fit result ────────────────────────────────────────────────────────
        fit_card = tk.Frame(self, bg=CARD, padx=12, pady=10,
                            highlightbackground=ACC, highlightthickness=1)
        fit_card.pack(padx=PAD, pady=(PAD, 0), fill="x")

        tk.Label(fit_card, text="Best Fit",
                 font=("Segoe UI", 10, "bold"), bg=CARD, fg=FG).pack(anchor="w", pady=(0, 4))

        self.fit_label = tk.Label(fit_card, text="Need ≥ 2 data points with different positions",
                                  font=MONO, bg=CARD, fg="#555")
        self.fit_label.pack(anchor="w")

        fit_btn_row = tk.Frame(fit_card, bg=CARD)
        fit_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(fit_btn_row, text="Compute Fit",
                   command=self._compute_fit).pack(side="left", padx=(0, 4))
        ttk.Button(fit_btn_row, text="Copy for timing.py",
                   command=self._copy_fit).pack(side="left")

        # ── Control row ───────────────────────────────────────────────────────
        ctrl_row = tk.Frame(self, bg=BG)
        ctrl_row.pack(padx=PAD, pady=PAD, fill="x")
        self.monitor_btn = ttk.Button(ctrl_row, text="▶  Start Monitoring",
                                      command=self._toggle_monitoring)
        self.monitor_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(ctrl_row, text="Save CSV", command=self._save_csv).pack(
            side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(ctrl_row, text="Clear Data", command=self._clear).pack(
            side="left", expand=True, fill="x", padx=(4, 0))

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Set left and right bounds, then start monitoring.")
        tk.Label(self, textvariable=self.status_var, font=("Segoe UI", 9),
                 bg=ACC, fg=FG, anchor="w", padx=8, pady=4).pack(fill="x", side="bottom")

    # ── Bound picking ─────────────────────────────────────────────────────────

    def _pick_bound(self, which: str):
        self._picking = True
        self.status_var.set(f"Click to set the {which} bound of the fishing zone…")
        overlay = tk.Toplevel(self)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.15)
        overlay.attributes("-topmost", True)
        overlay.config(cursor="crosshair", bg=BG)

        canvas = tk.Canvas(overlay, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            overlay.winfo_screenwidth() // 2, 40,
            text=f"Click to set the {which} bound  •  Esc to cancel",
            fill=HOT, font=("Segoe UI", 12, "bold"),
        )

        def on_click(event):
            x = event.x_root
            overlay.destroy()
            self.after(50, lambda: self._save_bound(which, x))

        overlay.bind("<Button-1>", on_click)
        overlay.bind("<Escape>", lambda _: self._cancel_pick(overlay))

    def _save_bound(self, which: str, x: int):
        setattr(self, f"{which}_bound", x)
        lbl = getattr(self, f"{which}_lbl")
        lbl.config(text=f"x = {x}", fg=FG)
        self.status_var.set(f"{which.capitalize()} bound set → x={x}")
        self._picking = False

    def _cancel_pick(self, overlay):
        overlay.destroy()
        self._picking = False
        self.status_var.set("Bound pick cancelled.")

    # ── Monitoring ────────────────────────────────────────────────────────────

    def _toggle_monitoring(self):
        if self.monitoring:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self):
        self.monitoring = True
        self.state = State.IDLE
        self.monitor_btn.config(text="■  Stop Monitoring")
        self.status_var.set("Monitoring — hold left-click in game to cast.")
        self._listener = _mouse_lib.Listener(on_click=self._on_mouse_event)
        self._listener.daemon = True
        self._listener.start()

    def _stop_monitoring(self):
        self.monitoring = False
        self.state = State.IDLE
        self.monitor_btn.config(text="▶  Start Monitoring")
        self.status_var.set("Stopped.")
        if hasattr(self, "_listener"):
            self._listener.stop()

    def _on_mouse_event(self, x, y, button, pressed):
        if button != _mouse_lib.Button.left or self._picking:
            return
        if self.state == State.IDLE and pressed:
            self.cast_start = time.time()
            self.state = State.CASTING
            self.after(0, lambda: self.status_var.set("Casting… release to record hold time."))
        elif self.state == State.CASTING and not pressed:
            hold_ms = (time.time() - self.cast_start) * 1000.0
            self.state = State.WAITING_BOBBER
            self.after(0, lambda h=hold_ms: self._prompt_bobber(h))

    # ── Bobber pick ───────────────────────────────────────────────────────────

    def _prompt_bobber(self, hold_ms: float):
        self._picking = True
        self.status_var.set(f"Hold: {hold_ms:.0f}ms — click where the bobber landed.")
        overlay = tk.Toplevel(self)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.15)
        overlay.attributes("-topmost", True)
        overlay.config(cursor="crosshair", bg=BG)

        canvas = tk.Canvas(overlay, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            overlay.winfo_screenwidth() // 2, 40,
            text=f"Hold = {hold_ms:.0f}ms  •  Click where the bobber landed  •  Esc to discard",
            fill=HOT, font=("Segoe UI", 12, "bold"),
        )

        def on_click(event):
            raw_x = event.x_root
            overlay.destroy()
            self.after(50, lambda: self._record(hold_ms, raw_x))

        overlay.bind("<Button-1>", on_click)
        overlay.bind("<Escape>", lambda _: self._discard(overlay))

    def _record(self, hold_ms: float, raw_x: int):
        self._picking = False
        self.state = State.IDLE
        if self.left_bound is None or self.right_bound is None:
            self.status_var.set("Bounds not set — point discarded.")
            return

        span = self.right_bound - self.left_bound
        if span <= 0:
            self.status_var.set("Invalid bounds (left ≥ right) — point discarded.")
            return

        position = (raw_x - self.left_bound) / span * 7.0
        position = max(0.0, min(7.0, position))
        rel_x = raw_x - self.left_bound
        self.data.append((hold_ms, position, rel_x))
        self._refresh_table()
        self.status_var.set(
            f"Recorded: hold={hold_ms:.0f}ms → pos={position:.2f}  |  Cast again to continue.")

    def _discard(self, overlay):
        overlay.destroy()
        self._picking = False
        self.state = State.IDLE
        self.status_var.set("Discarded. Cast again to continue.")

    # ── Table ─────────────────────────────────────────────────────────────────

    def _refresh_table(self):
        self.table.config(state="normal")
        self.table.delete("1.0", "end")
        if not self.data:
            self.table.insert("end", "  (no data yet)\n")
        else:
            for i, (hold, pos, raw) in enumerate(self.data, 1):
                self.table.insert("end", f"  {i:>2}.  {hold:>8.0f}    {pos:>6.2f}    {raw}\n")
        self.table.config(state="disabled")

    # ── Fit ───────────────────────────────────────────────────────────────────

    def _compute_fit(self):
        if len(self.data) < 2:
            self.fit_label.config(text="Need ≥ 2 data points.", fg="#888")
            return

        xs = [pos for _, pos, _ in self.data]
        ys = [hold for hold, _, _ in self.data]
        n  = len(xs)

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        ss_xx  = sum((x - mean_x) ** 2 for x in xs)
        ss_xy  = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

        if abs(ss_xx) < 1e-9:
            self.fit_label.config(
                text="All points at same position — vary your cast distance.", fg="#888")
            return

        slope    = ss_xy / ss_xx
        intercept = mean_y - slope * mean_x
        min_ms   = intercept
        max_ms   = intercept + slope * 7.0

        self._fit_min = min_ms
        self._fit_max = max_ms
        self.fit_label.config(
            text=f"MIN_HOLD_MS = {min_ms:.1f}    MAX_HOLD_MS = {max_ms:.1f}", fg=HOT)

    def _copy_fit(self):
        if not hasattr(self, "_fit_min"):
            self._compute_fit()
        if not hasattr(self, "_fit_min"):
            return
        text = (f"MIN_HOLD_MS: float = {self._fit_min:.1f}\n"
                f"MAX_HOLD_MS: float = {self._fit_max:.1f}")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Copied! Paste into timing.py.")

    # ── CSV export ────────────────────────────────────────────────────────────

    def _save_csv(self):
        if not self.data:
            self.status_var.set("No data to save.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="calibration.csv",
            title="Save calibration data",
        )
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["hold_ms", "position", "rel_x"])
            for hold, pos, raw in self.data:
                writer.writerow([f"{hold:.2f}", f"{pos:.4f}", raw])
        self.status_var.set(f"Saved {len(self.data)} rows → {path}")

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _clear(self):
        self.data.clear()
        self._refresh_table()
        if hasattr(self, "_fit_min"):
            del self._fit_min, self._fit_max
        self.fit_label.config(text="Need ≥ 2 data points with different positions", fg="#555")
        self.status_var.set("Data cleared.")

    def _on_close(self):
        self._stop_monitoring()
        self.destroy()


if __name__ == "__main__":
    CalibrationApp().mainloop()
