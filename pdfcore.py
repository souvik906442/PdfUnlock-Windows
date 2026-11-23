"""PdfUnlock core logic (no GUI): unlock, signature-stamp removal, password store."""
import base64
import ctypes
import hashlib
import json
import os
import sys
from ctypes import wintypes

import pymupdf as fitz


# ---------------------------------------------------------------- fingerprint
def fingerprint(path: str) -> str:
    """Same idea as the Android app: SHA-256 of first 64 KB + file size."""
    md = hashlib.sha256()
    with open(path, "rb") as f:
        md.update(f.read(65536))
    md.update(str(os.path.getsize(path)).encode())
    return md.hexdigest()


# ------------------------------------------------------------- password store
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    inp = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _enc(text: str) -> str:
    raw = text.encode("utf-8")
    if sys.platform == "win32":
        raw = _dpapi(raw, True)  # encrypted with the Windows user account key
    return base64.b64encode(raw).decode()


def _dec(s: str) -> str:
    raw = base64.b64decode(s)
    if sys.platform == "win32":
        raw = _dpapi(raw, False)
    return raw.decode("utf-8")


class PasswordStore:
    LAST = "last_used_password"

    def __init__(self, path: str | None = None):
        if path is None:
            base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
            path = os.path.join(base, "PdfUnlock", "passwords.json")
        self.path = path

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _store(self, d: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def save(self, key: str, password: str) -> None:
        try:
            d = self._load()
            d[key] = _enc(password)
            self._store(d)
        except Exception:
            pass

    def get(self, key: str):
        s = self._load().get(key)
        if not s:
            return None
        try:
            return _dec(s)
        except Exception:
            return None

    def forget(self, key: str) -> None:
        d = self._load()
        if d.pop(key, None) is not None:
            self._store(d)

    def forget_all(self) -> None:
        self._store({})

    def save_last(self, password: str) -> None:
        self.save(self.LAST, password)

    def get_last(self):
        return self.get(self.LAST)


# --------------------------------------------------------------------- unlock
OK, WRONG, ERROR = "ok", "wrong", "error"


def _remove_sig_stamp(doc) -> None:
    """The unlocked copy is rewritten, so it can't keep a valid signature: drop the stamp."""
    try:
        for page in doc:
            for w in list(page.widgets() or []):
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    page.delete_widget(w)
    except Exception:
        pass  # best effort: never block unlocking


def unlock(path: str, password: str):
    """Returns (outcome, unlocked_pdf_bytes_or_error_message)."""
    try:
        doc = fitz.open(path)
        try:
            if doc.needs_pass:
                if not doc.authenticate(password):
                    return WRONG, None
            _remove_sig_stamp(doc)
            data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
        finally:
            doc.close()
        return OK, data
    except Exception as e:  # noqa: BLE001
        return ERROR, str(e)


# ------------------------------------------------------------------ thumbnails
def _locked_thumbs_enabled() -> bool:
    """Installer option: also show thumbnails of password-protected PDFs whose password is saved."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\PdfUnlock") as k:
            return int(winreg.QueryValueEx(k, "LockedThumbnails")[0]) == 1
    except Exception:
        return False


def make_thumbnail(pdf_path: str, png_path: str, size: int) -> bool:
    """Renders page 1 as a PNG whose longest side is `size` px. Used by the Explorer thumbnail provider."""
    doc = fitz.open(pdf_path)
    try:
        if doc.needs_pass:
            if not _locked_thumbs_enabled():
                return False
            pw = PasswordStore().get(fingerprint(pdf_path))
            if not pw or not doc.authenticate(pw):
                return False
        if doc.page_count < 1:
            return False
        page = doc[0]
        r = page.rect
        scale = max(size, 16) / max(r.width, r.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        pix.save(png_path)
        return True
    finally:
        doc.close()
