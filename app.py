"""PdfUnlock for Windows - open password-protected PDFs, view them, select/copy text,
save an unlocked copy. Plain-text files (.txt, .log, ...) open in an editable text view."""
import os
import sys
import base64
import codecs
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import pymupdf as fitz

import pdfcore

APP = "PDF Unlock"
BG = "#e9e9ee"
SEL_COLOR = "#2f7bff"

# Files with these extensions open in the editable text view
TEXT_EXTS = {
    ".txt", ".log", ".md", ".csv", ".tsv", ".json", ".xml", ".ini", ".cfg", ".conf",
    ".yaml", ".yml", ".bat", ".cmd", ".reg", ".srt", ".nfo", ".py", ".js", ".css",
    ".html", ".htm", ".c", ".cpp", ".h", ".java", ".sh",
}
MAX_EDIT_BYTES = 30 * 1024 * 1024
ENC_NAMES = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8 with BOM", "utf-16": "UTF-16",
             "cp1252": "Windows-1252", "latin-1": "Latin-1"}


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


def is_editable_text(path):
    """True if the file should open in the text editor (by extension, not a PDF in disguise)."""
    if os.path.splitext(path)[1].lower() not in TEXT_EXTS:
        return False
    try:
        if os.path.getsize(path) > MAX_EDIT_BYTES:
            return False
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    if head.startswith(b"%PDF"):
        return False
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return True
    return b"\x00" not in head


def decode_text(raw):
    """bytes -> (text, encoding name that round-trips it)."""
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


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

        self.mode = "pdf"         # "pdf" (rendered view) or "text" (editable text)
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
        self.words = {}           # page index -> list of words (for selecting / copying)
        self.sel = None           # ((page, word), (page, word)) current selection
        self._drag_anchor = None

        self.tzoom = 1.0          # text view zoom
        self.t_enc = "utf-8"
        self.t_nl = "\n"

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if start_path:
            self.after(100, lambda: self.open_pdf(start_path))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open file…", command=self.ask_open).pack(side="left")
        self.save_btn = ttk.Button(bar, text="Save unlocked copy…", command=self.save_copy, state="disabled")
        self.save_btn.pack(side="left", padx=6)
        self.txt_save_btn = ttk.Button(bar, text="Save", command=lambda: self.save_text())
        self.txt_saveas_btn = ttk.Button(bar, text="Save as…", command=lambda: self.save_text(True))
        self.sep = ttk.Separator(bar, orient="vertical")
        self.sep.pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="−", width=3, command=lambda: self.zoom_by(1 / 1.2)).pack(side="left")
        self.zoom_lbl = ttk.Label(bar, text="100%", width=6, anchor="center")
        self.zoom_lbl.pack(side="left")
        ttk.Button(bar, text="+", width=3, command=lambda: self.zoom_by(1.2)).pack(side="left")
        self.fit_btn = ttk.Button(bar, text="Fit width", command=self.fit_width)
        self.fit_btn.pack(side="left", padx=6)
        self.wrap_var = tk.BooleanVar(value=True)
        self.wrap_chk = ttk.Checkbutton(bar, text="Word wrap", variable=self.wrap_var, command=self._toggle_wrap)
        ttk.Button(bar, text="Forget saved passwords", command=self.forget).pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        # ---- PDF / rendered view
        self.pdf_area = ttk.Frame(body)
        self.canvas = tk.Canvas(self.pdf_area, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self.pdf_area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb = sb
        self.pdf_area.pack(fill="both", expand=True)

        # ---- editable text view
        self.text_area = ttk.Frame(body)
        self.tfont = tkfont.Font(family="Consolas", size=12)
        self.text = tk.Text(self.text_area, wrap="word", undo=True, maxundo=-1, font=self.tfont,
                            bg="white", fg="#111", insertbackground="#111", padx=10, pady=8,
                            borderwidth=0, highlightthickness=0, selectbackground=SEL_COLOR,
                            selectforeground="white", inactiveselectbackground="#9cc0ff")
        tsb = ttk.Scrollbar(self.text_area, orient="vertical", command=self.text.yview)
        txsb = ttk.Scrollbar(self.text_area, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=tsb.set, xscrollcommand=txsb.set)
        txsb.pack(side="bottom", fill="x")
        tsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.status = tk.StringVar(value="Open a PDF or text file to start (Ctrl+O)")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(8, 3)).pack(fill="x")

        # ---- context menus
        self.pdf_menu = tk.Menu(self, tearoff=0)
        self.pdf_menu.add_command(label="Copy", command=self.copy_selection)
        self.pdf_menu.add_command(label="Select all", command=self.select_all)
        self.text_menu = tk.Menu(self, tearoff=0)
        self.text_menu.add_command(label="Undo", command=lambda: self.text.event_generate("<<Undo>>"))
        self.text_menu.add_command(label="Redo", command=lambda: self.text.event_generate("<<Redo>>"))
        self.text_menu.add_separator()
        self.text_menu.add_command(label="Cut", command=lambda: self.text.event_generate("<<Cut>>"))
        self.text_menu.add_command(label="Copy", command=lambda: self.text.event_generate("<<Copy>>"))
        self.text_menu.add_command(label="Paste", command=lambda: self.text.event_generate("<<Paste>>"))
        self.text_menu.add_separator()
        self.text_menu.add_command(label="Select all", command=self._text_select_all)

        # ---- canvas (PDF) bindings
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Triple-Button-1>", self._on_triple)
        self.canvas.bind("<Button-3>", lambda e: self._popup(self.pdf_menu, e))

        # ---- text widget bindings
        t = self.text
        t.bind("<Control-a>", self._text_select_all)
        t.bind("<Control-A>", self._text_select_all)
        t.bind("<Control-o>", lambda e: (self.ask_open(), "break")[1])   # Tk's own Ctrl+O inserts a newline
        t.bind("<Control-s>", lambda e: (self.save_text(), "break")[1])
        t.bind("<Control-S>", lambda e: (self.save_text(True), "break")[1])
        t.bind("<Control-MouseWheel>", lambda e: (self.zoom_by(1.1 if e.delta > 0 else 1 / 1.1), "break")[1])
        t.bind("<Button-3>", lambda e: self._popup(self.text_menu, e))
        t.bind("<<Modified>>", lambda e: self._update_title())

        # ---- global shortcuts
        self.bind("<Control-o>", lambda e: self.ask_open())
        self.bind("<Control-s>", lambda e: self.save_copy())
        self.bind("<Control-S>", lambda e: self.save_text(True) if self.mode == "text" else None)
        self.bind("<Control-c>", self.copy_selection)
        self.bind("<Control-a>", self.select_all)
        self.bind("<Control-plus>", lambda e: self.zoom_by(1.2))
        self.bind("<Control-equal>", lambda e: self.zoom_by(1.2))
        self.bind("<Control-minus>", lambda e: self.zoom_by(1 / 1.2))
        self.bind("<Prior>", lambda e: self.canvas.yview_scroll(-1, "pages"))
        self.bind("<Next>", lambda e: self.canvas.yview_scroll(1, "pages"))

    def _popup(self, menu, e):
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def _set_mode(self, mode):
        self.mode = mode
        self.pdf_area.pack_forget()
        self.text_area.pack_forget()
        for w in (self.save_btn, self.txt_save_btn, self.txt_saveas_btn, self.wrap_chk):
            w.pack_forget()
        if mode == "text":
            self.text_area.pack(fill="both", expand=True)
            self.txt_save_btn.pack(side="left", padx=(6, 0), before=self.sep)
            self.txt_saveas_btn.pack(side="left", padx=6, before=self.sep)
            self.wrap_chk.pack(side="left", padx=6, after=self.fit_btn)
            self.fit_btn.state(["disabled"])
            self.zoom_lbl.config(text=f"{int(self.tzoom * 100)}%")
        else:
            self.pdf_area.pack(fill="both", expand=True)
            self.save_btn.pack(side="left", padx=6, before=self.sep)
            self.fit_btn.state(["!disabled"])
            self.zoom_lbl.config(text=f"{int(self.zoom * 100)}%")

    def _update_title(self):
        if not self.src_name:
            self.title(APP)
            return
        star = "*" if self.mode == "text" and self.text.edit_modified() else ""
        self.title(f"{star}{self.src_name} - {APP}")

    def _on_yscroll(self, a, b):
        self.sb.set(a, b)
        self._render_visible()

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")

    def _on_ctrl_wheel(self, e):
        self.zoom_by(1.1 if e.delta > 0 else 1 / 1.1)
        return "break"

    def _on_resize(self, _e):
        if self.doc and self.fit_mode:
            self.fit_width()
        else:
            self._layout()

    # ------------------------------------------------------------- opening
    def ask_open(self):
        exts = " ".join("*" + x for x in [".pdf"] + sorted(TEXT_EXTS))
        p = filedialog.askopenfilename(
            title="Open file",
            filetypes=[("PDF and text files", exts), ("PDF files", "*.pdf"),
                       ("Text files", "*.txt *.log *.md *.csv"), ("All files", "*.*")])
        if p:
            self.open_pdf(p)

    def open_pdf(self, path):
        """Opens a PDF (or any file PyMuPDF can render); plain-text files go to the text editor."""
        if not self._confirm_discard():
            return
        if not os.path.isfile(path):
            messagebox.showerror(APP, "File not found:\n" + path)
            return
        if is_editable_text(path):
            self.open_text(path)
            return
        self._clear()
        self._set_mode("pdf")
        self.src_path = path
        self.src_name = os.path.basename(path)
        self._update_title()
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
        self.canvas.config(cursor="xterm")
        self.fit_mode = True
        self.fit_width()
        self.canvas.yview_moveto(0)
        self._render_visible()
        self.status.set(f"{self.src_name} - {self.doc.page_count} pages "
                        f"(unlocked, original file unchanged) - drag to select text, Ctrl+C to copy")

    def _clear(self):
        if self.doc:
            self.doc.close()
        self.doc = None
        self.data = None
        self.images.clear()
        self.items.clear()
        self.words.clear()
        self.sel = None
        self._drag_anchor = None
        self.canvas.delete("all")
        self.canvas.config(cursor="")
        self.save_btn.config(state="disabled")

    # ------------------------------------------------------------ text mode
    def open_text(self, path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            messagebox.showerror(APP, f"Couldn't open this file.\n\n{e}")
            return
        text, enc = decode_text(raw)
        if "\r\n" in text:
            nl = "\r\n"
        elif "\r" in text and "\n" not in text:
            nl = "\r"
        else:
            nl = "\n"
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        self._clear()
        self.src_path = path
        self.src_name = os.path.basename(path)
        self.t_enc, self.t_nl = enc, nl
        self._set_mode("text")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.text.mark_set("insert", "1.0")
        self.text.see("1.0")
        self.text.focus_set()
        self._update_title()
        nl_name = {"\r\n": "Windows", "\n": "Unix", "\r": "Mac"}[nl]
        self.status.set(f"{self.src_name} - editing ({ENC_NAMES.get(enc, enc)}, {nl_name} line endings) - Ctrl+S to save")

    def save_text(self, save_as=False):
        if self.mode != "text":
            return False
        path = self.src_path
        if save_as or not path:
            ext = os.path.splitext(self.src_name or "")[1] or ".txt"
            p = filedialog.asksaveasfilename(
                title="Save as", defaultextension=ext,
                initialdir=os.path.dirname(path) if path else None,
                initialfile=self.src_name or "untitled.txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
            if not p:
                return False
            path = p
        content = self.text.get("1.0", "end-1c")
        if self.t_nl != "\n":
            content = content.replace("\n", self.t_nl)
        note = ""
        try:
            data = content.encode(self.t_enc)
        except UnicodeEncodeError:
            data = content.encode("utf-8")
            self.t_enc = "utf-8"
            note = " (saved as UTF-8 because of special characters)"
        tmp = path + ".~tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            messagebox.showerror(APP, f"Save failed:\n{e}")
            return False
        self.src_path = path
        self.src_name = os.path.basename(path)
        self.text.edit_modified(False)
        self._update_title()
        self.status.set(f"Saved: {path}{note}")
        return True

    def _confirm_discard(self):
        """True if it's OK to leave the current text file (saved, or user chose not to)."""
        if self.mode != "text" or not self.text.edit_modified():
            return True
        r = messagebox.askyesnocancel(APP, f"Save changes to {self.src_name}?")
        if r is None:
            return False
        if r:
            return self.save_text()
        return True

    def _text_select_all(self, _e=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        return "break"

    def _toggle_wrap(self):
        self.text.config(wrap="word" if self.wrap_var.get() else "none")

    # ---------------------------------------------------------------- view
    def zoom_by(self, f):
        if self.mode == "text":
            self.tzoom = min(max(self.tzoom * f, 0.5), 5.0)
            self.tfont.configure(size=max(6, round(12 * self.tzoom)))
            self.zoom_lbl.config(text=f"{int(self.tzoom * 100)}%")
        else:
            self.set_zoom(self.zoom * f)

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
        self._draw_sel()

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
        self.canvas.tag_raise("sel")

    # --------------------------------------------------- select & copy text
    def _page_words(self, i):
        w = self.words.get(i)
        if w is None:
            try:
                w = self.doc[i].get_text("words")  # (x0, y0, x1, y1, word, block, line, wordno)
            except Exception:
                w = []
            self.words[i] = w
        return w

    def _hit(self, cx, cy):
        """Canvas point -> (page, word index) of the nearest word, or None."""
        if not self.doc or not self.page_y:
            return None
        pg = len(self.page_y) - 1
        for i, y in enumerate(self.page_y):
            if cy < y + self.page_h[i] + 6:
                pg = i
                break
        words = self._page_words(pg)
        if not words:
            return None
        ox = (self._cw - self.page_w[pg]) // 2
        px = (cx - ox) / self.zoom
        py = (cy - self.page_y[pg]) / self.zoom
        best, bd = 0, None
        for k, w in enumerate(words):
            dx = w[0] - px if px < w[0] else (px - w[2] if px > w[2] else 0)
            dy = w[1] - py if py < w[1] else (py - w[3] if py > w[3] else 0)
            d = dy * dy * 4 + dx * dx
            if bd is None or d < bd:
                best, bd = k, d
                if d == 0:
                    break
        return (pg, best)

    def _sel_words(self):
        if not self.sel:
            return []
        a, b = self.sel
        if a > b:
            a, b = b, a
        out = []
        for p in range(a[0], b[0] + 1):
            ws = self._page_words(p)
            lo = a[1] if p == a[0] else 0
            hi = b[1] if p == b[0] else len(ws) - 1
            for k in range(lo, min(hi, len(ws) - 1) + 1):
                out.append((p, ws[k]))
        return out

    def _sel_text(self):
        out, last = [], None
        for p, w in self._sel_words():
            key = (p, w[5], w[6])
            if last is not None:
                out.append(" " if key == last else "\n")
            out.append(w[4])
            last = key
        return "".join(out)

    def _draw_sel(self):
        self.canvas.delete("sel")
        if not self.sel or not self.page_y:
            return
        z = self.zoom
        boxes = {}
        for p, w in self._sel_words():
            key = (p, w[5], w[6])
            b = boxes.get(key)
            if b is None:
                boxes[key] = [w[0], w[1], w[2], w[3]]
            else:
                b[0], b[1] = min(b[0], w[0]), min(b[1], w[1])
                b[2], b[3] = max(b[2], w[2]), max(b[3], w[3])
        for (p, _blk, _ln), b in boxes.items():
            if p >= len(self.page_y):
                continue
            ox = (self._cw - self.page_w[p]) // 2
            oy = self.page_y[p]
            self.canvas.create_rectangle(ox + b[0] * z, oy + b[1] * z, ox + b[2] * z, oy + b[3] * z,
                                         fill=SEL_COLOR, outline="", stipple="gray50", tags="sel")
        self.canvas.tag_raise("sel")

    def _on_press(self, e):
        self.canvas.focus_set()
        if not self.doc:
            return
        self._drag_anchor = self._hit(self.canvas.canvasx(e.x), self.canvas.canvasy(e.y))
        self.sel = None
        self._draw_sel()

    def _on_drag(self, e):
        if not self.doc or self._drag_anchor is None:
            return
        if e.y < 0:
            self.canvas.yview_scroll(-1, "units")
        elif e.y > self.canvas.winfo_height():
            self.canvas.yview_scroll(1, "units")
        h = self._hit(self.canvas.canvasx(e.x), self.canvas.canvasy(e.y))
        if h is None:
            return
        self.sel = (self._drag_anchor, h)
        self._draw_sel()

    def _on_double(self, e):
        """Double-click selects a word."""
        h = self._hit(self.canvas.canvasx(e.x), self.canvas.canvasy(e.y))
        self._drag_anchor = None
        if h:
            self.sel = (h, h)
            self._draw_sel()

    def _on_triple(self, e):
        """Triple-click selects the whole line."""
        h = self._hit(self.canvas.canvasx(e.x), self.canvas.canvasy(e.y))
        self._drag_anchor = None
        if not h:
            return
        ws = self._page_words(h[0])
        key = (ws[h[1]][5], ws[h[1]][6])
        idx = [k for k, w in enumerate(ws) if (w[5], w[6]) == key]
        self.sel = ((h[0], min(idx)), (h[0], max(idx)))
        self._draw_sel()

    def select_all(self, _e=None):
        if self.mode != "pdf" or not self.doc:
            return
        first = last = None
        for p in range(len(self.page_y)):
            n = len(self._page_words(p))
            if n:
                if first is None:
                    first = (p, 0)
                last = (p, n - 1)
        self.sel = (first, last) if first else None
        self._draw_sel()
        return "break"

    def copy_selection(self, _e=None):
        if self.mode != "pdf" or not self.doc or not self.sel:
            return
        t = self._sel_text()
        if not t:
            return
        self.clipboard_clear()
        self.clipboard_append(t)
        self.update()
        self.status.set(f"Copied {len(t)} characters")
        return "break"

    # ------------------------------------------------------------- actions
    def save_copy(self):
        if self.mode == "text":
            self.save_text()
            return
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
        if not self._confirm_discard():
            return
        self._clear()
        self.destroy()


def main():
    # Explorer thumbnail provider calls:  PdfUnlock.exe --thumb <pdf> <png> <size>
    if len(sys.argv) >= 5 and sys.argv[1] == "--thumb":
        try:
            ok = pdfcore.make_thumbnail(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        except Exception:
            ok = False
        sys.exit(0 if ok else 1)
    _dpi_aware()
    start = sys.argv[1] if len(sys.argv) > 1 else None
    App(start).mainloop()


if __name__ == "__main__":
    main()
