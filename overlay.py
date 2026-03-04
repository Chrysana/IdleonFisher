import sys
import tkinter as tk
from tkinter import ttk
import threading
import time
from pathlib import Path

from cast_executor import execute_cast
from timing import get_hold_time

MIN_POSITION = 1.0   # dead zone below this position
_CAST_HINT   = "Click where the fish is  •  Esc to stop"

BG   = "#1a1a2e"
CARD = "#16213e"
ACC  = "#0f3460"
HOT  = "#e94560"
FG   = "#eaeaea"
MONO = ("Consolas", 10)

# When bundled with PyInstaller --onefile, data files land in sys._MEIPASS
_HERE = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("IdleOn Fishing Assistant")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.left_bound:  int | None = None
        self.right_bound: int | None = None
        self._casting = False
        self._picking = False

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

        tk.Label(self, text="IdleOn Fishing Assistant",
                 font=("Segoe UI", 14, "bold"), bg=BG, fg=HOT).pack(pady=(PAD, 4), padx=PAD)
        tk.Label(self, text="Click where the fish is — the app casts to that spot",
                 font=("Segoe UI", 9), bg=BG, fg="#888").pack(padx=PAD, pady=(0, PAD))

        # Load bound marker images (fail silently if missing)
        self._img_left  = self._load_image("left_bound_marker.png")
        self._img_right = self._load_image("right_bound_marker.png")

        # ── Bounds card ───────────────────────────────────────────────────────
        bounds_card = tk.Frame(self, bg=CARD, padx=12, pady=10,
                               highlightbackground=ACC, highlightthickness=1)
        bounds_card.pack(padx=PAD, fill="x")

        tk.Label(bounds_card, text="Fishing Zone Bounds",
                 font=("Segoe UI", 10, "bold"), bg=CARD, fg=FG).pack(anchor="w", pady=(0, 6))

        for side, attr, img in (
            ("Left",  "left",  self._img_left),
            ("Right", "right", self._img_right),
        ):
            row = tk.Frame(bounds_card, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{side} Bound:", font=("Segoe UI", 9),
                     bg=CARD, fg="#aaa", width=12, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="Not set", font=MONO, bg=CARD, fg="#aaa")
            lbl.pack(side="left", padx=(4, 8))
            setattr(self, f"{attr}_lbl", lbl)
            if img:
                tk.Label(row, image=img, bg=CARD).pack(side="left", padx=(0, 6))
            ttk.Button(row, text=f"Pick {side}",
                       command=lambda a=attr: self._pick_bound(a)).pack(side="right")

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(padx=PAD, pady=PAD, fill="x")
        self.cast_btn = ttk.Button(btn_row, text="▶  Start Casting",
                                   command=self._open_casting_overlay)
        self.cast_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(btn_row, text="Reset", command=self._reset).pack(
            side="left", expand=True, fill="x", padx=(4, 0))

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Set left and right bounds, then start casting.")
        tk.Label(self, textvariable=self.status_var, font=("Segoe UI", 9),
                 bg=ACC, fg=FG, anchor="w", padx=8, pady=4).pack(fill="x", side="bottom")

    def _load_image(self, filename: str):
        try:
            return tk.PhotoImage(file=str(_HERE / filename))
        except Exception:
            return None

    # ── Bound picking ──────────────────────────────────────────────────────────

    def _pick_bound(self, which: str):
        self._picking = True
        self.status_var.set(f"Click to set the {which} bound of the fishing zone…")
        ov = tk.Toplevel(self)
        ov.attributes("-fullscreen", True)
        ov.attributes("-alpha", 0.15)
        ov.attributes("-topmost", True)
        ov.config(cursor="crosshair", bg=BG)

        canvas = tk.Canvas(ov, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            ov.winfo_screenwidth() // 2, 40,
            text=f"Click to set the {which} bound  •  Esc to cancel",
            fill=HOT, font=("Segoe UI", 12, "bold"),
        )

        def on_click(event):
            x = event.x_root
            ov.destroy()
            self.after(50, lambda: self._save_bound(which, x))

        ov.bind("<Button-1>", on_click)
        ov.bind("<Escape>", lambda _: self._cancel_pick(ov))

    def _save_bound(self, which: str, x: int):
        setattr(self, f"{which}_bound", x)
        getattr(self, f"{which}_lbl").config(text=f"x = {x}", fg=FG)
        self.status_var.set(f"{which.capitalize()} bound set → x={x}")
        self._picking = False

    def _cancel_pick(self, ov):
        ov.destroy()
        self._picking = False
        self.status_var.set("Bound pick cancelled.")

    # ── Casting overlay ────────────────────────────────────────────────────────

    def _open_casting_overlay(self):
        if self.left_bound is None or self.right_bound is None:
            self.status_var.set("Set both bounds first.")
            return
        if (self.right_bound - self.left_bound) <= 0:
            self.status_var.set("Invalid bounds — left must be less than right.")
            return

        ov = tk.Toplevel(self)
        ov.attributes("-fullscreen", True)
        ov.attributes("-alpha", 0.15)
        ov.attributes("-topmost", True)
        ov.config(cursor="crosshair", bg=BG)
        ov.focus_force()

        canvas = tk.Canvas(ov, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        info = canvas.create_text(
            ov.winfo_screenwidth() // 2, 40,
            text=_CAST_HINT, fill=HOT, font=("Segoe UI", 12, "bold"),
        )

        def on_click(event):
            if self._casting or self._picking:
                return
            self._casting = True

            raw_x   = event.x_root
            click_y = event.y_root
            span    = self.right_bound - self.left_bound
            pos     = max(MIN_POSITION, min(7.0, (raw_x - self.left_bound) / span * 7.0))
            hold_ms = get_hold_time(pos)

            self.status_var.set(f"Casting to pos={pos:.2f}  hold={hold_ms:.0f}ms")

            # Hide overlay so the game window receives the pynput mouse events
            ov.withdraw()

            def do_cast():
                time.sleep(0.15)   # give the OS time to process the window hide
                execute_cast(hold_ms, position=(raw_x, click_y))
                self._casting = False
                def restore():
                    ov.deiconify()
                    ov.attributes("-topmost", True)
                    ov.focus_force()
                    canvas.itemconfig(info, text=_CAST_HINT)
                    self.status_var.set(f"Cast complete.  pos={pos:.2f}  hold={hold_ms:.0f}ms")
                self.after(0, restore)

            threading.Thread(target=do_cast, daemon=True).start()

        canvas.bind("<Button-1>", on_click)
        ov.bind("<Escape>", lambda _: self._close_overlay(ov))
        self.status_var.set("Overlay open — click where the fish is.  Esc to stop.")

    def _close_overlay(self, ov):
        self._casting = False
        if ov.winfo_exists():
            ov.destroy()
        self.status_var.set("Casting stopped. Click Start Casting to begin again.")

    def _reset(self):
        self.left_bound = None
        self.right_bound = None
        self.left_lbl.config(text="Not set", fg="#aaa")
        self.right_lbl.config(text="Not set", fg="#aaa")
        self.status_var.set("Reset. Set left and right bounds, then start casting.")

    def _on_close(self):
        self.destroy()
