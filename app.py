"""PdfUnlock for Windows - open password-protected PDFs, view, save an unlocked copy."""
import os
import sys
import base64
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pymupdf as fitz

import pdfcore

APP = "PDF Unlock"
BG = "#e9e9ee"


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _dpi_aware():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class PasswordDialog(tk.Toplevel):
    def __init__(self, parent, name, prefill="", wrong=False):
        super().__init__(parent)
        self.title("Enter password")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        f = ttk.Frame(self, padding=18)
        f.pack()
        ttk.Label(f, text="This PDF is locked", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text=name, foreground="#666").pack(anchor="w", pady=(0, 10))
        self.var = tk.StringVar(value=prefill)
        self.entry = ttk.Entry(f, textvariable=self.var, show="•", width=34)
        self.entry.pack(fill="x")
        self.show = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Show password", variable=self.show,
                        command=lambda: self.entry.config(show="" if self.show.get() else "•")
                        ).pack(anchor="w", pady=(6, 0))
        if wrong:
            ttk.Label(f, text="The password is incorrect.", foreground="#d33").pack(anchor="w", pady=(6, 0))
        b = ttk.Frame(f)
        b.pack(fill="x", pady=(14, 0))
        ttk.Button(b, text="Unlock", command=self._ok).pack(side="right")
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + 120
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = self.var.get()
        self.destroy()


class App(tk.Tk):
    def __init__(self, start_path=None):
        super().__init__()
        self.title(APP)
        try:
            self._icon = tk.PhotoImage(file=resource_path("icon.png"))
            self.iconphoto(True, self._icon)
        except Exception:
            pass
        self.geometry("900x800")
        self.minsize(560, 420)
        self.store = pdfcore.PasswordStore()

        self.src_path = None
        self.src_name = None
        self.fp = None
        self.data = None          # unlocked PDF bytes
        self.doc = None           # fitz doc of unlocked bytes
        self.zoom = 1.0
        self.fit_mode = True
        self.page_y = []          # top y of each page
        self.page_h = []
        self.page_w = []
        self.images = {}          # page index -> PhotoImage
        self.items = {}           # page index -> canvas image id

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if start_path:
            self.after(100, lambda: self.open_pdf(start_path))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open PDF…", command=self.ask_open).pack(side="left")
        self.save_btn = ttk.Button(bar, text="Save unlocked copy…", command=self.save_copy, state="disabled")
        self.save_btn.pack(side="left", padx=6)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="−", width=3, command=lambda: self.set_zoom(self.zoom / 1.2)).pack(side="left")
        self.zoom_lbl = ttk.Label(bar, text="100%", width=6, anchor="center")
        self.zoom_lbl.pack(side="left")
        ttk.Button(bar, text="+", width=3, command=lambda: self.set_zoom(self.zoom * 1.2)).pack(side="left")
        ttk.Button(bar, text="Fit width", command=self.fit_width).pack(side="left", padx=6)
        ttk.Button(bar, text="Forget saved passwords", command=self.forget).pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb = sb

        self.status = tk.StringVar(value="Open a PDF to start (Ctrl+O)")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(8, 3)).pack(fill="x")

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.bind("<Control-o>", lambda e: self.ask_open())
        self.bind("<Control-s>", lambda e: self.save_copy())
        self.bind("<Control-plus>", lambda e: self.set_zoom(self.zoom * 1.2))
        self.bind("<Control-equal>", lambda e: self.set_zoom(self.zoom * 1.2))
        self.bind("<Control-minus>", lambda e: self.set_zoom(self.zoom / 1.2))
        self.bind("<Prior>", lambda e: self.canvas.yview_scroll(-1, "pages"))
        self.bind("<Next>", lambda e: self.canvas.yview_scroll(1, "pages"))

    def _on_yscroll(self, a, b):
        self.sb.set(a, b)
        self._render_visible()

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")

    def _on_ctrl_wheel(self, e):
        self.set_zoom(self.zoom * (1.1 if e.delta > 0 else 1 / 1.1))
        return "break"

    def _on_resize(self, _e):
        if self.doc and self.fit_mode:
            self.fit_width()
        else:
            self._layout()

    # ------------------------------------------------------------- opening
    def ask_open(self):
        p = filedialog.askopenfilename(title="Open PDF",
                                       filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if p:
            self.open_pdf(p)

    def open_pdf(self, path):
        if not os.path.isfile(path):
            messagebox.showerror(APP, "File not found:\n" + path)
            return
        self.src_path = path
        self.src_name = os.path.basename(path)
        self.title(f"{self.src_name} - {APP}")
        self._clear()
        self.status.set("Unlocking…")
        self.update_idletasks()
        try:
            self.fp = pdfcore.fingerprint(path)
        except Exception as e:
            self.fp = None
            self.status.set(f"Error: {e}")
            return
        saved = self.store.get(self.fp)
        self._try(saved or "", from_user=False)

    def _try(self, password, from_user):
        outcome, res = pdfcore.unlock(self.src_path, password)
        if outcome == pdfcore.OK:
            if from_user and password:
                self.store.save(self.fp, password)
                self.store.save_last(password)
            self._show(res)
        elif outcome == pdfcore.WRONG:
            if not from_user:
                self.store.forget(self.fp)  # saved password no longer works
            prefill = "" if from_user else (self.store.get_last() or "")
            self.status.set("This PDF is locked")
            d = PasswordDialog(self, self.src_name, prefill=prefill, wrong=from_user)
            if d.result is None:
                self.status.set("Cancelled - PDF is still locked (Ctrl+O to open another)")
            else:
                self._try(d.result, from_user=True)
        else:
            self.status.set("Couldn't open this file")
            messagebox.showerror(APP, f"Couldn't open this file.\n\n{res}")

    def _show(self, data):
        self.data = data
        self.doc = fitz.open("pdf", data)
        self.save_btn.config(state="normal")
        self.fit_mode = True
        self.fit_width()
        self.canvas.yview_moveto(0)
        self._render_visible()
        self.status.set(f"{self.src_name} - {self.doc.page_count} pages (unlocked, original file unchanged)")

    def _clear(self):
        if self.doc:
            self.doc.close()
        self.doc = None
        self.data = None
        self.images.clear()
        self.items.clear()
        self.canvas.delete("all")
        self.save_btn.config(state="disabled")

    # ---------------------------------------------------------------- view
    def fit_width(self):
        if not self.doc:
            return
        cw = max(self.canvas.winfo_width() - 24, 100)
        widest = max(p.rect.width for p in self.doc)
        self.fit_mode = True
        self._apply_zoom(cw / widest)

    def set_zoom(self, z):
        if not self.doc:
            return
        self.fit_mode = False
        self._apply_zoom(min(max(z, 0.2), 6.0))

    def _apply_zoom(self, z):
        top = self.canvas.yview()[0]
        self.zoom = z
        self.zoom_lbl.config(text=f"{int(z * 100)}%")
        self.images.clear()
        self.items.clear()
        self._layout()
        self.canvas.yview_moveto(top)
        self._render_visible()

    def _layout(self):
        self.canvas.delete("all")
        self.items.clear()
        if not self.doc:
            return
        gap = 12
        y = gap
        self.page_y, self.page_w, self.page_h = [], [], []
        maxw = 0
        for p in self.doc:
            w, h = int(p.rect.width * self.zoom), int(p.rect.height * self.zoom)
            self.page_y.append(y)
            self.page_w.append(w)
            self.page_h.append(h)
            y += h + gap
            maxw = max(maxw, w)
        cw = max(self.canvas.winfo_width(), maxw + 2 * gap)
        self.canvas.configure(scrollregion=(0, 0, cw, y))
        self._cw = cw
        for i in range(len(self.page_y)):
            x0 = (cw - self.page_w[i]) // 2
            self.canvas.create_rectangle(x0, self.page_y[i], x0 + self.page_w[i], self.page_y[i] + self.page_h[i],
                                         fill="white", outline="#bbb", tags=f"bg{i}")

    def _render_visible(self):
        if not self.doc or not self.page_y:
            return
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        margin = 600
        for i, y in enumerate(self.page_y):
            vis = y + self.page_h[i] >= top - margin and y <= bottom + margin
            if vis and i not in self.items:
                try:
                    pix = self.doc[i].get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
                    img = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")))
                except Exception:
                    continue
                self.images[i] = img
                x0 = (self._cw - self.page_w[i]) // 2
                self.items[i] = self.canvas.create_image(x0, y, anchor="nw", image=img)
            elif not vis and i in self.items:  # free memory for far-away pages
                self.canvas.delete(self.items.pop(i))
                self.images.pop(i, None)

    # ------------------------------------------------------------- actions
    def save_copy(self):
        if not self.data:
            return
        stem = os.path.splitext(self.src_name)[0]
        p = filedialog.asksaveasfilename(
            title="Save unlocked copy", defaultextension=".pdf",
            initialdir=os.path.dirname(self.src_path), initialfile=f"{stem}_unlocked.pdf",
            filetypes=[("PDF files", "*.pdf")])
        if not p:
            return
        try:
            with open(p, "wb") as f:
                f.write(self.data)
            self.status.set(f"Saved: {p}")
        except Exception as e:
            messagebox.showerror(APP, f"Save failed:\n{e}")

    def forget(self):
        if messagebox.askyesno(APP, "Remove all saved passwords from this PC?"):
            self.store.forget_all()
            self.status.set("Saved passwords removed")

    def _close(self):
        self._clear()
        self.destroy()


def main():
    _dpi_aware()
    start = sys.argv[1] if len(sys.argv) > 1 else None
    App(start).mainloop()


if __name__ == "__main__":
    main()
