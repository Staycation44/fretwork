"""
ASSETS - locates and reads the page's bundled static files

Paths resolve from this file, not the working directory, so serve.py works
from anywhere. Required files are read at startup so a partial checkout fails
before the socket binds.
"""

import pathlib

STATIC_DIR = pathlib.Path(__file__).resolve().parent / 'static'

# glob -> content type; each file's URL path comes from its path under STATIC_DIR
STATIC_GLOBS = (
    ('js/*.js', 'text/javascript; charset=utf-8'),
    ('css/*.css', 'text/css; charset=utf-8'),
)

REQUIRED = ('index.html', 'js/main.js', 'css/app.css')


def read_text(name):
    return (STATIC_DIR / name).read_text(encoding='utf-8')


def check_present():
    missing = [n for n in REQUIRED if not (STATIC_DIR / n).is_file()]
    if missing:
        raise FileNotFoundError(
            f"missing static file(s) under {STATIC_DIR}: {', '.join(missing)}")


# URL path -> (bytes, content type), built by walking STATIC_DIR at startup.
# Keys never come from a request, so path traversal is impossible by construction.
def load_static():
    check_present()
    served = {}
    for pattern, content_type in STATIC_GLOBS:
        for path in sorted(STATIC_DIR.glob(pattern)):
            url = '/static/' + path.relative_to(STATIC_DIR).as_posix()
            served[url] = (path.read_bytes(), content_type)
    return served
