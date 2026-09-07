"""
BOOTSTRAP - fetches and caches the Bootstrap stylesheet, with a fallback

Cached under CACHE_DIR so the served page never contacts a CDN and keeps
working offline after the first run. FALLBACK_CSS lives here because it is
exactly the branch taken when the fetch returns nothing.
"""

import http.client
import pathlib
import urllib.error
import urllib.request

import config

BOOTSTRAP_VERSION = '5.3.8'
BOOTSTRAP_URL = (f"https://cdn.jsdelivr.net/npm/bootstrap@{BOOTSTRAP_VERSION}"
                 f"/dist/css/bootstrap.min.css")
BOOTSTRAP_MIN_BYTES = 100_000  # sanity floor - a captive-portal HTML page is way under this

FALLBACK_CSS = """<style>
  :root { --bs-body-bg:#1a1a1c; --bs-body-color:#eaeaea; --bs-border-color:#34343a;
          --bs-tertiary-bg:#232326; --bs-secondary-color:#9a9aa2;
          --bs-font-monospace:ui-monospace,SFMono-Regular,Consolas,monospace; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bs-body-bg); color:var(--bs-body-color);
         font:13px/1.45 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif; }
  .d-none { display:none !important; }
  .d-flex { display:flex; } .flex-wrap { flex-wrap:wrap; } .flex-fill { flex:1; }
  .align-items-center { align-items:center; } .align-items-baseline { align-items:baseline; }
  .gap-2 { gap:.5rem; } .mt-2 { margin-top:.5rem; } .mb-2 { margin-bottom:.5rem; }
  .mb-0 { margin-bottom:0; } .ms-auto { margin-left:auto; } .w-auto { width:auto; }
  .px-3 { padding-left:1rem; padding-right:1rem; } .pt-3 { padding-top:1rem; }
  .pb-2 { padding-bottom:.5rem; } .p-2 { padding:.5rem; }
  .border-bottom { border-bottom:1px solid var(--bs-border-color); }
  .bg-body { background:var(--bs-body-bg); }
  .h6 { font-size:15px; } .fw-semibold { font-weight:600; }
  .small, .form-text { font-size:11px; }
  .text-secondary, .form-text { color:var(--bs-secondary-color); }
  .form-control, .form-control-sm { background:var(--bs-tertiary-bg); color:var(--bs-body-color);
    border:1px solid var(--bs-border-color); border-radius:6px; padding:5px 9px; font-size:13px; outline:none; }
  .form-control:focus { border-color:#b71fb7; }
  .btn { background:var(--bs-tertiary-bg); color:var(--bs-body-color); cursor:pointer;
    border:1px solid var(--bs-border-color); border-radius:6px; padding:5px 10px; font-size:12px; }
  .btn:hover { border-color:#b71fb7; }
  .btn-primary, .btn.active { background:#b71fb7; border-color:#b71fb7; color:#fff; }
  .btn-link { background:none; border:0; }
  .btn-group { display:flex; } .btn-group .btn { border-radius:0; }
  .btn-group .btn:first-child { border-radius:6px 0 0 6px; }
  .btn-group .btn:last-child { border-radius:0 6px 6px 0; }
  table { border-collapse:collapse; width:100%; }
  th, td { border-bottom:1px solid #26262b; text-align:left; }
  tbody tr:hover td { background:#26262c; }
  .badge { display:inline-block; padding:2px 8px; font-size:11px; }
  .rounded-pill { border-radius:9px; }
  .dropdown-menu { display:none; background:var(--bs-tertiary-bg);
    border:1px solid var(--bs-border-color); border-radius:8px; }
  .dropdown-menu.show { display:block; }
  .shadow { box-shadow:0 10px 30px rgba(0,0,0,.55); }
  .form-check { position:relative; }
  .form-check-input { position:absolute; left:4px; top:5px; }
  .input-group { display:flex; align-items:center; gap:4px; }
  .input-group .form-control { width:100%; }
</style>"""


def bootstrap_path():
    return pathlib.Path(config.CACHE_DIR) / f"bootstrap-{BOOTSTRAP_VERSION}.min.css"


# returns the cached CSS bytes, downloading once if needed, or None if unavailable
def ensure_bootstrap(enabled=True):
    if not enabled:
        return None

    path = bootstrap_path()
    if path.is_file() and path.stat().st_size >= BOOTSTRAP_MIN_BYTES:
        return path.read_bytes()

    print(f"Fetching Bootstrap {BOOTSTRAP_VERSION} (one time) ...", end='', flush=True)
    try:
        with urllib.request.urlopen(BOOTSTRAP_URL, timeout=20) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError,
            http.client.HTTPException) as exc:
        print(f" failed ({exc}) - using built-in styles")
        return None

    if len(data) < BOOTSTRAP_MIN_BYTES:
        print(" failed (unexpected response) - using built-in styles")
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f" cached {len(data) // 1024} KB -> {path}")
    return data
