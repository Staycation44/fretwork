"""
SERVE - browse a metrics spreadsheet in a browser instead of Excel

Loads the newest metrics .xlsx for a header and serves it as a sortable,
filterable table on localhost. Clicking a row renders that song's graph on
demand - same PNG render.py produces, written to RENDER_DIR and cached in
memory for the life of the process.

    python serve.py
    python serve.py --header FullTest --port 8080
    python serve.py --xlsx metrics/Local_metrics_09072026-1022.xlsx

Stdlib http.server - no web framework, nothing added to requirements.txt.
Binds 127.0.0.1 only. WSL2 forwards localhost, so the URL opens in a Windows
browser as-is.

Bootstrap 5.3 supplies the CSS. It is downloaded once into CACHE_DIR and then
served same-origin from /bootstrap.css, so the page has no CDN dependency at
view time and keeps working offline after the first run. --no-bootstrap skips
it and falls back to the built-in styles.

Reads the spreadsheet, not the cache - run analyze.py first. The cache is only
touched (lazily) the first time a graph is requested.

The page itself lives in web/ - see web/static/ for its markup and scripts.
"""

import argparse

import config
from web import assets, banner, boot, bootstrap, frames, page
from web.graph import GraphRenderer
from web.server import MetricsServer


def serve(header=None, xlsx_path=None, cache_path=None, port=8000, out_dir=None,
          use_bootstrap=True):
    header = header or config.HEADER
    bootstrap_css = bootstrap.ensure_bootstrap(use_bootstrap)

    xlsx_path, sheets = frames.load_frames(header, xlsx_path)
    total = sum(len(df) for df in sheets.values())
    source = f"{xlsx_path.name}  -  {total} rows  -  {', '.join(sheets)}"

    body = page.render_page(
        f"Fretwork - {header}", source, bootstrap_css,
        boot.boot_json(frames.frames_payload(sheets)))

    httpd = MetricsServer(
        port, body, assets.load_static(), bootstrap_css,
        GraphRenderer(header, cache_path, out_dir))

    with httpd:
        banner.print_startup(xlsx_path, sheets, total, bootstrap_css, port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            banner.print_stopped()


def main():
    parser = argparse.ArgumentParser(description="Serve a metrics spreadsheet as a local web page.")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--xlsx', default=None, help="explicit metrics .xlsx (overrides header lookup)")
    parser.add_argument('--cache', default=None, help="explicit cache path, used for on-demand graphs")
    parser.add_argument('--out-dir', default=None, help="PNG output directory for rendered graphs")
    parser.add_argument('--port', type=int, default=8000, help="localhost port (default 8000)")
    parser.add_argument('--no-bootstrap', action='store_true',
                        help="skip the Bootstrap fetch and use the built-in styles")
    args = parser.parse_args()

    serve(header=args.header, xlsx_path=args.xlsx, cache_path=args.cache,
          port=args.port, out_dir=args.out_dir, use_bootstrap=not args.no_bootstrap)


if __name__ == '__main__':
    main()
