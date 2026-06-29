import ctypes
import sys
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

from app.controller import AppController


def _set_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main():
    """Main entry point"""
    _set_dpi_awareness()
    try:
        app = AppController()
        app.run()
    except Exception as e:
        # Persist crash details so errors are visible even when launched via pythonw (double-click).
        log_dir = Path.home() / "AppData" / "Local" / "VoxScribe" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        crash_log = log_dir / "startup_crash.log"

        with open(crash_log, "w", encoding="utf-8") as f:
            f.write(f"Unhandled startup error: {e}\n\n")
            f.write(traceback.format_exc())

        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "VoxScribe Startup Error",
                f"Application failed to start.\n\nError: {e}\n\n"
                f"Detailed log saved to:\n{crash_log}",
            )
            root.destroy()
        except Exception:
            pass

        raise


if __name__ == "__main__":
    main()
