// PdfUnlock thumbnail provider (Explorer thumbnails for PDF files).
// Tiny in-process COM DLL: it copies the PDF to a temp file, runs
//   PdfUnlock.exe --thumb <pdf> <png> <size>
// and hands the PNG back to Explorer. All PDF work happens in PdfUnlock.exe.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objidl.h>
#include <shlwapi.h>
#include <shlobj.h>
#include <thumbcache.h>
#include <gdiplus.h>
#include <new>
#include <string>

#ifdef _MSC_VER
#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "uuid.lib")
#endif

// {B4E3C8A2-6D1F-4F5B-9A47-2C7E5D9F1A63}
static const CLSID CLSID_PdfUnlockThumb =
    {0xb4e3c8a2, 0x6d1f, 0x4f5b, {0x9a, 0x47, 0x2c, 0x7e, 0x5d, 0x9f, 0x1a, 0x63}};

// IIDs defined here so we do not depend on which import library provides them.
// IInitializeWithStream {b824b49d-22ac-4161-ac8a-9916e8fa3f7f}
static const IID kIID_InitWithStream =
    {0xb824b49d, 0x22ac, 0x4161, {0xac, 0x8a, 0x99, 0x16, 0xe8, 0xfa, 0x3f, 0x7f}};
// IThumbnailProvider {e357fccd-a995-4576-b01f-234630154e96}
static const IID kIID_ThumbProvider =
    {0xe357fccd, 0xa995, 0x4576, {0xb0, 0x1f, 0x23, 0x46, 0x30, 0x15, 0x4e, 0x96}};

static LONG g_refs = 0;

static bool GetExePath(std::wstring &out) {
    wchar_t buf[MAX_PATH * 2];
    DWORD len = sizeof(buf);
    if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\PdfUnlock", L"ExePath", RRF_RT_REG_SZ,
                     nullptr, buf, &len) != ERROR_SUCCESS)
        return false;
    out = buf;
    return true;
}

static bool CopyStreamToFile(IStream *s, const std::wstring &path) {
    STATSTG st = {};
    if (SUCCEEDED(s->Stat(&st, STATFLAG_NONAME)) && st.cbSize.QuadPart > 200ull * 1024 * 1024)
        return false;  // too big for a thumbnail
    LARGE_INTEGER zero = {};
    s->Seek(zero, STREAM_SEEK_SET, nullptr);
    HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_TEMPORARY, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    char buf[65536];
    bool ok = true;
    for (;;) {
        ULONG n = 0;
        HRESULT hr = s->Read(buf, sizeof(buf), &n);
        if (FAILED(hr)) { ok = false; break; }
        if (n == 0) break;
        DWORD w = 0;
        if (!WriteFile(h, buf, n, &w, nullptr) || w != n) { ok = false; break; }
    }
    CloseHandle(h);
    return ok;
}

static bool RunRenderer(const std::wstring &exe, const std::wstring &pdf, const std::wstring &png, UINT cx) {
    std::wstring cmd = L"\"" + exe + L"\" --thumb \"" + pdf + L"\" \"" + png + L"\" " + std::to_wstring(cx);
    STARTUPINFOW si = {};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi = {};
    if (!CreateProcessW(nullptr, &cmd[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi))
        return false;
    bool ok = false;
    if (WaitForSingleObject(pi.hProcess, 20000) == WAIT_OBJECT_0) {
        DWORD code = 1;
        GetExitCodeProcess(pi.hProcess, &code);
        ok = (code == 0);
    } else {
        TerminateProcess(pi.hProcess, 1);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return ok;
}

class Provider : public IInitializeWithStream, public IThumbnailProvider {
    LONG m_ref = 1;
    IStream *m_stream = nullptr;

public:
    Provider() { InterlockedIncrement(&g_refs); }
    ~Provider() {
        if (m_stream) m_stream->Release();
        InterlockedDecrement(&g_refs);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void **ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == kIID_InitWithStream)
            *ppv = static_cast<IInitializeWithStream *>(this);
        else if (riid == kIID_ThumbProvider)
            *ppv = static_cast<IThumbnailProvider *>(this);
        else {
            *ppv = nullptr;
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_ref); }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG r = InterlockedDecrement(&m_ref);
        if (r == 0) delete this;
        return r;
    }

    // IInitializeWithStream
    STDMETHODIMP Initialize(IStream *stream, DWORD) override {
        if (m_stream) return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
        m_stream = stream;
        m_stream->AddRef();
        return S_OK;
    }

    // IThumbnailProvider
    STDMETHODIMP GetThumbnail(UINT cx, HBITMAP *phbmp, WTS_ALPHATYPE *pdwAlpha) override {
        if (!m_stream) return E_UNEXPECTED;
        *phbmp = nullptr;
        *pdwAlpha = WTSAT_RGB;

        std::wstring exe;
        if (!GetExePath(exe)) return E_FAIL;

        wchar_t dir[MAX_PATH], tmp[MAX_PATH];
        if (!GetTempPathW(MAX_PATH, dir)) return E_FAIL;
        if (!GetTempFileNameW(dir, L"pdu", 0, tmp)) return E_FAIL;  // creates the file
        std::wstring pdf = tmp, png = pdf + L".png";

        HRESULT hr = E_FAIL;
        if (CopyStreamToFile(m_stream, pdf) && RunRenderer(exe, pdf, png, cx)) {
            Gdiplus::GdiplusStartupInput in;
            ULONG_PTR token = 0;
            if (Gdiplus::GdiplusStartup(&token, &in, nullptr) == Gdiplus::Ok) {
                {
                    Gdiplus::Bitmap bmp(png.c_str());
                    if (bmp.GetLastStatus() == Gdiplus::Ok &&
                        bmp.GetHBITMAP(Gdiplus::Color(255, 255, 255, 255), phbmp) == Gdiplus::Ok && *phbmp)
                        hr = S_OK;
                }
                Gdiplus::GdiplusShutdown(token);
            }
        }
        DeleteFileW(pdf.c_str());
        DeleteFileW(png.c_str());
        return hr;
    }
};

class Factory : public IClassFactory {
    LONG m_ref = 1;

public:
    STDMETHODIMP QueryInterface(REFIID riid, void **ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory *>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_ref); }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG r = InterlockedDecrement(&m_ref);
        if (r == 0) delete this;
        return r;
    }
    STDMETHODIMP CreateInstance(IUnknown *outer, REFIID riid, void **ppv) override {
        if (outer) return CLASS_E_NOAGGREGATION;
        Provider *p = new (std::nothrow) Provider();
        if (!p) return E_OUTOFMEMORY;
        HRESULT hr = p->QueryInterface(riid, ppv);
        p->Release();
        return hr;
    }
    STDMETHODIMP LockServer(BOOL lock) override {
        if (lock) InterlockedIncrement(&g_refs);
        else InterlockedDecrement(&g_refs);
        return S_OK;
    }
};

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID *ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (!IsEqualCLSID(rclsid, CLSID_PdfUnlockThumb)) return CLASS_E_CLASSNOTAVAILABLE;
    Factory *f = new (std::nothrow) Factory();
    if (!f) return E_OUTOFMEMORY;
    HRESULT hr = f->QueryInterface(riid, ppv);
    f->Release();
    return hr;
}

STDAPI DllCanUnloadNow(void) {
    return g_refs == 0 ? S_OK : S_FALSE;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(inst);
    return TRUE;
}
