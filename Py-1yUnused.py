#!/usr/bin/env python3

import argparse
import os
import stat
import sys
import time
import tkinter as tk
from tkinter import ttk
import string


def get_drives():
    return [f'{letter}:\\' for letter in string.ascii_uppercase if os.path.exists(f'{letter}:\\')]


def is_executable(path):
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    if os.name == "nt":
        return path.lower().endswith(('.exe', '.bat', '.cmd', '.com', '.ps1'))
    return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def scan_path(root, cutoff_ts):
    unused = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=None, followlinks=False):
        try:
            dir_stat = os.stat(dirpath)
            if dir_stat.st_atime < cutoff_ts:
                unused.append((dirpath, 'directory', False))
        except OSError:
            pass

        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue

            if st.st_atime < cutoff_ts:
                ty = 'file'
                if is_executable(path):
                    ty = 'program'
                unused.append((path, ty, True))
    return unused


def parse_args():
    parser = argparse.ArgumentParser(description='Find files/folders/programs not accessed since a given threshold.')
    parser.add_argument('root', nargs='?', default='.', help='Root path to scan (default: current directory)')
    parser.add_argument('--days', type=int, default=365, help='Number of days since last access (default: 365)')
    parser.add_argument('--include-hidden', action='store_true', help='Include hidden files and folders')
    return parser.parse_args()


def main():
    # Check if arguments provided, if yes, use CLI mode
    if len(sys.argv) > 1:
        args = parse_args()
        if not os.path.exists(args.root):
            print(f'Error: path does not exist: {args.root}', file=sys.stderr)
            sys.exit(1)

        cutoff_ts = time.time() - args.days * 24 * 3600
        unused = scan_path(os.path.abspath(args.root), cutoff_ts)

        if not unused:
            print(f'No items not used since {args.days} days found under {args.root}')
            return

        print(f'Items not used since {args.days} days or more:')
        for path, ty, _ in sorted(unused, key=lambda item: item[0]):
            print(f'[{ty}] {path}')
        return

    # GUI mode
    root = tk.Tk()
    root.title("Unused Files Scanner")

    drives = get_drives()
    check_vars = [tk.IntVar() for _ in drives]

    tk.Label(root, text="Select drives to scan:").pack(pady=10)

    frame = ttk.Frame(root)
    frame.pack(pady=10)

    for i, drive in enumerate(drives):
        ttk.Checkbutton(frame, text=drive, variable=check_vars[i]).pack(anchor='w')

    tk.Label(root, text="Days since last access:").pack(pady=5)
    days_var = tk.StringVar(value="365")
    days_entry = ttk.Entry(root, textvariable=days_var)
    days_entry.pack(pady=5)

    result_text = tk.Text(root, height=20, width=80)
    result_text.pack(pady=10)

    def scan():
        try:
            days = int(days_var.get())
        except ValueError:
            result_text.delete(1.0, tk.END)
            result_text.insert(tk.END, "Invalid number of days")
            return

        selected_drives = [drive for drive, var in zip(drives, check_vars) if var.get()]
        if not selected_drives:
            result_text.delete(1.0, tk.END)
            result_text.insert(tk.END, "No drives selected")
            return

        cutoff_ts = time.time() - days * 24 * 3600
        all_unused = []
        for drive in selected_drives:
            unused = scan_path(drive, cutoff_ts)
            all_unused.extend(unused)

        result_text.delete(1.0, tk.END)
        if not all_unused:
            result_text.insert(tk.END, f'No items not used since {days} days found on selected drives')
            return

        result_text.insert(tk.END, f'Items not used since {days} days or more:\n')
        for path, ty, _ in sorted(all_unused, key=lambda item: item[0]):
            result_text.insert(tk.END, f'[{ty}] {path}\n')

    ttk.Button(root, text="Scan", command=scan).pack(pady=10)

    root.mainloop()


if __name__ == '__main__':
    main()
