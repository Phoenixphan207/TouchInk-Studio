"""Crash-reporting entrypoint for Windows double-click launchers."""
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _log(details):
    folder = Path(__file__).resolve().parent / 'logs'
    try:
        folder.mkdir(exist_ok=True)
        with (folder / 'launch.log').open('a', encoding='utf-8') as f:
            f.write(f'{datetime.now().isoformat(timespec="seconds")}\n{details}\n')
    except OSError:
        pass


def main():
    try:
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (OSError, AttributeError):
                pass
        import tkinter as tk
        from tkinter import messagebox
        from app import Studio
        root = tk.Tk()
        def callback_error(exc, value, tb):
            details = ''.join(traceback.format_exception(exc, value, tb))
            _log(details)
            print(details, file=sys.stderr)
            try:
                messagebox.showerror('TouchInk Studio error',
                                     'An operation failed. Details were saved to logs\\launch.log.\n\n'
                                     + details[-700:], parent=root)
            except Exception:
                pass
        root.report_callback_exception = callback_error
        Studio(root)
        root.mainloop()
        return 0
    except Exception:
        details = traceback.format_exc()
        _log(details)
        print(details, file=sys.stderr)
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk._default_root
            if root is None:
                root = tk.Tk()
                root.withdraw()
            messagebox.showerror('TouchInk Studio could not start',
                                 'An error occurred. Review logs\\launch.log for details.\n\n'
                                 + details[-1100:])
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
