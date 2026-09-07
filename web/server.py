"""
SERVER - the HTTP server, carrying the handler's dependencies
"""

import http.server

from web.handler import MetricsHandler

BIND_HOST = '127.0.0.1'


class MetricsServer(http.server.ThreadingHTTPServer):
    """Threading server whose attributes are what MetricsHandler reads."""

    def __init__(self, port, body, static, bootstrap_css, graphs):
        self.body = body
        self.static = static
        self.bootstrap_css = bootstrap_css
        self.graphs = graphs
        super().__init__((BIND_HOST, port), MetricsHandler)
