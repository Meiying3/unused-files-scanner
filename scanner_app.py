#!/usr/bin/env python3

import argparse
import os
import stat
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk
import string
import threading


# ── Palette ───────────────────────────────────────────────────────────────────

BG        = "#12141c"
SURFACE   = "#1a1d2e"
SURFACE2  = "#222638"
BORDER    = "#2e3250"
TEXT      = "#e2e4f0"
MUTED     = "#5a6080"
ACCENT    = "#5b8dee"
ACCENT_DIM= "#1a2540"
GREEN     = "#4ecb8d"
AMBER     = "#f5a623"
RED       = "#f05a5a"

TWO_YEARS = 2 * 365 * 24 * 3600

TYPE_COLOR = {"file": ACCENT, "directory": GREEN, "program": AMBER}
TYPE_ICON  = {"file": "●", "directory": "▶", "program": "⚙"}


# ── Scanner logic ─────────────────────────────────────────────────────────────

def get_drives():
    if os.name == "nt":
        return [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]
    return [p for p in ["/", "/home", "/Volumes"] if os.path.exists(p)]


def is_executable(path):
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    if os.name == "nt":
        return path.lower().endswith((".exe", ".bat", ".cmd", ".com", ".ps1"))
    return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def scan_path(root, cutoff_ts, include_hidden=False, stop_event=None):
    # Returns list of (path, type, atime)
    unused = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=None, followlinks=False):
        if stop_event and stop_event.is_set():
            break
        dirnames[:] = [d for d in dirnames if include_hidden or not d.startswith(".")]
        try:
            ds = os.stat(dirpath)
            if ds.st_atime < cutoff_ts:
                unused.append((dirpath, "directory", ds.st_atime))
        except OSError:
            pass
        for name in filenames:
            if not include_hidden and name.startswith("."):
                continue
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st.st_atime < cutoff_ts:
                ty = "program" if is_executable(path) else "file"
                unused.append((path, ty, st.st_atime))
    return unused


# ── CLI mode ──────────────────────────────────────────────────────────────────

def run_cli():
    parser = argparse.ArgumentParser(description="Find files/folders/programs not accessed since a given threshold.")
    parser.add_argument("root", nargs="?", default=".", help="Root path to scan (default: current directory)")
    parser.add_argument("--days", type=int, default=365, help="Number of days since last access (default: 365)")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden files and folders")
    args = parser.parse_args()

    if not os.path.exists(args.root):
        print(f"Error: path does not exist: {args.root}", file=sys.stderr)
        sys.exit(1)

    cutoff_ts = time.time() - args.days * 24 * 3600
    unused = scan_path(os.path.abspath(args.root), cutoff_ts, include_hidden=args.include_hidden)

    if not unused:
        print(f"No items not used since {args.days} days found under {args.root}")
        return

    print(f"Items not used since {args.days} days or more:")
    for path, ty, atime in sorted(unused, key=lambda x: x[2]):
        date = time.strftime("%Y-%m-%d", time.localtime(atime))
        print(f"[{ty}] {date}  {path}")


# ── GUI ───────────────────────────────────────────────────────────────────────

class ScannerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Unused Files Scanner")
        self.geometry("1000x660")
        self.minsize(700, 480)
        self.configure(bg=BG)

        self._results_all = []
        self._filter = "all"
        self._drive_vars = {}
        self._stop_event = threading.Event()

        self._setup_styles()
        self._build_ui()
        self._populate_drives()

    # ── Styles ────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT,
                        fieldbackground=SURFACE, troughcolor=BORDER,
                        bordercolor=BORDER, relief="flat")

        style.configure("Treeview",
                        background=BG, foreground=TEXT,
                        fieldbackground=BG, rowheight=28,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading",
                        background=SURFACE, foreground=MUTED,
                        font=("Segoe UI", 9, "bold"),
                        relief="flat", borderwidth=0)
        style.map("Treeview",
                  background=[("selected", ACCENT_DIM)],
                  foreground=[("selected", ACCENT)])
        style.map("Treeview.Heading", relief=[("active", "flat")])

        style.configure("Vertical.TScrollbar",
                        background=SURFACE2, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, width=6)
        style.configure("Horizontal.TScrollbar",
                        background=SURFACE2, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, width=6)

        style.configure("TProgressbar",
                        troughcolor=BORDER, background=ACCENT,
                        bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

        style.configure("TCheckbutton",
                        background=SURFACE, foreground=TEXT,
                        font=("Segoe UI", 10), focuscolor=SURFACE)
        style.map("TCheckbutton",
                  background=[("active", SURFACE)],
                  foreground=[("active", ACCENT)])

        style.configure("TScale",
                        background=SURFACE, troughcolor=BORDER,
                        sliderrelief="flat", sliderthickness=14)
        style.map("TScale", background=[("active", SURFACE)])

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        topbar = tk.Frame(self, bg=SURFACE, height=46)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text="Unused Files Scanner",
                 bg=SURFACE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left", padx=20, pady=12)
        self._header_status = tk.Label(topbar, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9))
        self._header_status.pack(side="right", padx=20)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Body
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = tk.Frame(body, bg=SURFACE, width=240)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        def sidebar_gap(h=12):
            tk.Frame(sidebar, bg=SURFACE, height=h).pack()

        def sidebar_label(text):
            tk.Label(sidebar, text=text, bg=SURFACE, fg=MUTED,
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", padx=18)

        def sidebar_sep():
            sidebar_gap(12)
            tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=18)
            sidebar_gap(12)

        sidebar_gap(18)

        # atime warning on Windows
        if os.name == "nt":
            warn_frame = tk.Frame(sidebar, bg="#2a1a0a")
            warn_frame.pack(fill="x", padx=18)
            tk.Label(warn_frame,
                     text="⚠ Windows may not update last-access times. Results may be inaccurate.",
                     bg="#2a1a0a", fg=AMBER, font=("Segoe UI", 8),
                     justify="left", wraplength=190).pack(padx=8, pady=6, anchor="w")
            sidebar_gap(10)

        # Drives
        sidebar_label("DRIVES")
        sidebar_gap(8)
        self._drives_frame = tk.Frame(sidebar, bg=SURFACE)
        self._drives_frame.pack(fill="x", padx=18)

        sidebar_sep()

        # Days
        sidebar_label("DAYS SINCE LAST ACCESS")
        sidebar_gap(8)

        days_row = tk.Frame(sidebar, bg=SURFACE)
        days_row.pack(fill="x", padx=18)
        self._days_lbl = tk.Label(days_row, text="365",
                                  bg=SURFACE, fg=TEXT, font=("Segoe UI", 28, "bold"))
        self._days_lbl.pack(side="left")
        tk.Label(days_row, text=" days", bg=SURFACE, fg=MUTED,
                 font=("Segoe UI", 11)).pack(side="left", anchor="s", pady=6)

        self._days_var = tk.IntVar(value=365)
        self._days_var.trace_add("write", lambda *_: self._days_lbl.config(text=str(self._days_var.get())))

        ttk.Scale(sidebar, from_=30, to=730, variable=self._days_var,
                  command=lambda v: self._days_var.set(int(float(v)))
                  ).pack(fill="x", padx=18, pady=(8, 8))

        # Preset buttons
        presets = tk.Frame(sidebar, bg=SURFACE)
        presets.pack(fill="x", padx=18)
        for label, val in [("90d", 90), ("1 yr", 365), ("18mo", 548), ("2 yr", 730)]:
            tk.Button(presets, text=label,
                      command=lambda v=val: self._days_var.set(v),
                      bg=SURFACE2, fg=MUTED, activebackground=BORDER,
                      activeforeground=TEXT, relief="flat", bd=0,
                      font=("Segoe UI", 9), padx=8, pady=4,
                      cursor="hand2").pack(side="left", padx=2)

        sidebar_sep()

        # Scan + Stop buttons
        btn_row = tk.Frame(sidebar, bg=SURFACE)
        btn_row.pack(fill="x", padx=18)

        self._scan_btn = tk.Button(
            btn_row, text="▶   Scan",
            command=self._start_scan,
            bg=ACCENT_DIM, fg=ACCENT,
            activebackground=BORDER, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 11, "bold"), pady=10)
        self._scan_btn.pack(side="left", fill="x", expand=True)

        self._stop_btn = tk.Button(
            btn_row, text="■",
            command=self._stop_scan,
            bg=SURFACE2, fg=RED,
            activebackground=BORDER, activeforeground=RED,
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 11, "bold"), pady=10, padx=10)
        # hidden until a scan is running
        self._stop_btn.pack_forget()

        sidebar_gap(10)
        self._progress = ttk.Progressbar(sidebar, mode="indeterminate")

        # ── Results panel ─────────────────────────────────────────────────────
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        # Header
        res_hdr = tk.Frame(right, bg=SURFACE, height=46)
        res_hdr.pack(fill="x")
        res_hdr.pack_propagate(False)
        tk.Label(res_hdr, text="Results", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=18, pady=12)
        self._count_lbl = tk.Label(res_hdr, text="—", bg=SURFACE, fg=MUTED,
                                   font=("Segoe UI", 10))
        self._count_lbl.pack(side="right", padx=18)
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")

        # Filter bar
        fbar = tk.Frame(right, bg=SURFACE, height=40)
        fbar.pack(fill="x")
        fbar.pack_propagate(False)
        self._filter_btns = {}
        for label, key, color in [
            ("All",         "all",       TEXT),
            ("Files",       "file",      ACCENT),
            ("Directories", "directory", GREEN),
            ("Programs",    "program",   AMBER),
        ]:
            btn = tk.Button(fbar, text=label,
                            command=lambda k=key: self._set_filter(k),
                            bg=SURFACE, fg=MUTED,
                            activebackground=SURFACE2, activeforeground=color,
                            relief="flat", bd=0, cursor="hand2",
                            font=("Segoe UI", 9), padx=14, pady=8)
            btn.pack(side="left")
            self._filter_btns[key] = (btn, color)

        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")

        # Treeview
        tree_wrap = tk.Frame(right, bg=BG)
        tree_wrap.pack(fill="both", expand=True)

        self._tree = ttk.Treeview(tree_wrap, columns=("type", "date", "path"),
                                   show="headings", selectmode="browse")
        self._tree.heading("type", text="Type",           anchor="w")
        self._tree.heading("date", text="Last accessed",  anchor="w")
        self._tree.heading("path", text="Path",           anchor="w")
        self._tree.column("type", width=120, minwidth=100, stretch=False, anchor="w")
        self._tree.column("date", width=130, minwidth=110, stretch=False, anchor="w")
        self._tree.column("path", anchor="w")

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(right, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        hsb.pack(fill="x")

        for ty, color in TYPE_COLOR.items():
            self._tree.tag_configure(ty, foreground=color)
        self._tree.tag_configure("old",   foreground=RED)
        self._tree.tag_configure("empty", foreground=MUTED)

        self._tree.bind("<Double-1>", self._open_selected)

        # Status bar
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", side="bottom")
        sbar = tk.Frame(right, bg=SURFACE, height=28)
        sbar.pack(fill="x", side="bottom")
        sbar.pack_propagate(False)
        self._statusbar = tk.Label(sbar, text="Ready — select drives and click Scan",
                                   bg=SURFACE, fg=MUTED,
                                   font=("Segoe UI", 9), anchor="w")
        self._statusbar.pack(side="left", padx=14, pady=6)

        # Set default filter highlight
        self._set_filter("all")

    # ── Drives ────────────────────────────────────────────────────────────────

    def _populate_drives(self):
        for w in self._drives_frame.winfo_children():
            w.destroy()
        self._drive_vars.clear()
        for drive in get_drives():
            var = tk.BooleanVar(value=True)
            self._drive_vars[drive] = var
            ttk.Checkbutton(self._drives_frame, text=drive, variable=var).pack(anchor="w", pady=3)

    # ── Filter ────────────────────────────────────────────────────────────────

    def _set_filter(self, key):
        self._filter = key
        for k, (btn, color) in self._filter_btns.items():
            if k == key:
                btn.config(fg=color, bg=SURFACE2)
            else:
                btn.config(fg=MUTED, bg=SURFACE)
        self._render_results()

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _start_scan(self):
        selected = [d for d, v in self._drive_vars.items() if v.get()]
        if not selected:
            self._set_status("No drives selected.")
            return
        self._stop_event.clear()
        self._scan_btn.config(state="disabled", text="  Scanning…")
        self._stop_btn.pack(side="left", padx=(6, 0))
        self._progress.pack(fill="x", padx=18, pady=(0, 6))
        self._progress.start(12)
        self._clear_tree()
        self._count_lbl.config(text="—")
        days = self._days_var.get()
        self._set_status(f"Scanning {', '.join(selected)}…")
        threading.Thread(target=self._scan_worker, args=(selected, days), daemon=True).start()

    def _stop_scan(self):
        self._stop_event.set()
        self._set_status("Stopping…")

    def _scan_worker(self, drives, days):
        cutoff = time.time() - days * 24 * 3600
        try:
            results = []
            for d in drives:
                if self._stop_event.is_set():
                    break
                results.extend(scan_path(d, cutoff, stop_event=self._stop_event))
            results.sort(key=lambda x: x[2])
            stopped = self._stop_event.is_set()
            self.after(0, self._scan_done, results, days, stopped)
        except Exception as exc:
            self.after(0, self._scan_error, str(exc))

    def _scan_done(self, results, days, stopped):
        self._results_all = results
        self._progress.stop()
        self._progress.pack_forget()
        self._stop_btn.pack_forget()
        self._scan_btn.config(state="normal", text="▶   Scan")
        self._count_lbl.config(text=f"{len(results)} items")
        suffix = "  · scan stopped" if stopped else ""
        self._set_status(f"Found {len(results)} items  ·  threshold: {days} days{suffix}")
        self._set_filter("all")

    def _scan_error(self, msg):
        self._progress.stop()
        self._progress.pack_forget()
        self._stop_btn.pack_forget()
        self._scan_btn.config(state="normal", text="▶   Scan")
        self._set_status(f"Error: {msg}")

    # ── Open selected ─────────────────────────────────────────────────────────

    def _open_selected(self, _):
        sel = self._tree.selection()
        if not sel:
            return
        path = self._tree.item(sel[0], "values")[2]
        if not path or not os.path.exists(path):
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception:
            pass

    # ── Render ────────────────────────────────────────────────────────────────

    def _clear_tree(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

    def _render_results(self):
        self._clear_tree()
        filtered = (
            self._results_all if self._filter == "all"
            else [r for r in self._results_all if r[1] == self._filter]
        )
        if not filtered:
            msg = "No items match this filter." if self._results_all else "No unused items found."
            self._tree.insert("", "end", values=("", "", msg), tags=("empty",))
            return
        now = time.time()
        for path, ty, atime in filtered:
            icon  = f"{TYPE_ICON.get(ty, '·')}  {ty}"
            date  = time.strftime("%Y-%m-%d", time.localtime(atime))
            tag   = "old" if (now - atime) > TWO_YEARS else ty
            self._tree.insert("", "end", values=(icon, date, path), tags=(tag,))

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, msg):
        self._statusbar.config(text=msg)
        self._header_status.config(text=msg)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        run_cli()
    else:
        ScannerApp().mainloop()


if __name__ == "__main__":
    main()
