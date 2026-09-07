"""
BANNER - the terminal output around serve_forever
"""

from web.bootstrap import BOOTSTRAP_VERSION


def print_startup(xlsx_path, frames, total, bootstrap_css, port):
    style = (f"Bootstrap {BOOTSTRAP_VERSION} (served locally)"
             if bootstrap_css else "built-in fallback")
    print(f"\nServing {xlsx_path}")
    print(f"    {total} rows across {len(frames)} sheet(s): {', '.join(frames)}")
    print(f"    styles: {style}")
    print(f"\n    http://localhost:{port}\n")
    print("Ctrl+C to stop\n")


def print_stopped():
    print("\nStopped\n")
