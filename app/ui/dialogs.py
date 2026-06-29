import customtkinter as ctk
import tkinter as tk


class VoxMessageBox(ctk.CTkToplevel):
    def __init__(self, parent, message, title="Dialog", buttons=("OK",), default=0):
        super().__init__(parent)
        self._result = None
        self.title(title)
        width = 380
        height = 170
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.attributes("-topmost", True)
        if parent is not None:
            self.transient(parent)
        self.lift()
        self.focus_force()

        frame = ctk.CTkFrame(self)
        frame.pack(expand=True, fill="both", padx=18, pady=18)

        label = ctk.CTkLabel(
            frame,
            text=message,
            wraplength=320,
            justify="left",
            font=ctk.CTkFont(size=13),
        )
        label.pack(expand=True, fill="both", pady=(0, 12))

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.pack()

        button_widgets = []
        for button_text in buttons:
            button = ctk.CTkButton(
                button_row,
                text=button_text,
                width=92,
                command=lambda value=button_text: self._button(value),
            )
            button.pack(side="left", padx=6)
            button_widgets.append(button)

        self.update_idletasks()
        x, y = self._center_position(parent, width, height)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", True))

        if button_widgets:
            button_widgets[max(0, min(default, len(button_widgets) - 1))].focus_set()
            self.bind("<Return>", lambda _event: button_widgets[max(0, min(default, len(button_widgets) - 1))].invoke())
        self.bind("<Escape>", lambda _event: self._on_close())
        self.grab_set()
        self.wait_window()

    def _center_position(self, parent, width, height):
        try:
            if parent is not None and parent.winfo_exists() and parent.winfo_viewable():
                parent.update_idletasks()
                x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
                y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
                return x, y
        except Exception:
            pass
        return (
            max(0, (self.winfo_screenwidth() - width) // 2),
            max(0, (self.winfo_screenheight() - height) // 2),
        )

    def _button(self, value):
        self._result = value
        self.destroy()

    def _on_close(self):
        self._result = None
        self.destroy()


def _get_parent_window():
    root = getattr(tk, "_default_root", None)
    if root is None:
        return None
    try:
        if root.winfo_exists():
            return root
    except Exception:
        return None
    return None


def show_error(title, message, parent=None):
    VoxMessageBox(parent or _get_parent_window(), message, title=title, buttons=("OK",))


def show_warning(title, message, parent=None):
    VoxMessageBox(parent or _get_parent_window(), message, title=title, buttons=("OK",))


def show_info(title, message, parent=None):
    VoxMessageBox(parent or _get_parent_window(), message, title=title, buttons=("OK",))


def ask_yes_no(title, message, parent=None):
    box = VoxMessageBox(parent or _get_parent_window(), message, title=title, buttons=("Yes", "No"), default=0)
    return box._result == "Yes"


def ask_yes_no_cancel(title, message, parent=None):
    box = VoxMessageBox(parent or _get_parent_window(), message, title=title, buttons=("Yes", "No", "Cancel"), default=0)
    if box._result == "Yes":
        return True
    if box._result == "No":
        return False
    return None
