"""
PAGE - fills index.html's placeholders and returns the response body

One regex pass rather than chained replaces, so a value that happens to
contain __TOKEN__ text is never rewritten by a later substitution.
"""

import html
import re

from web import assets, bootstrap

_PLACEHOLDER = re.compile(r'__([A-Z]+)__')

BOOTSTRAP_LINK = '<link rel="stylesheet" href="/bootstrap.css">'


def bootstrap_head(bootstrap_css):
    return BOOTSTRAP_LINK if bootstrap_css else bootstrap.FALLBACK_CSS


def render_page(title, source, bootstrap_css, boot_json):
    values = {
        'TITLE': html.escape(title),
        'SOURCE': html.escape(source),
        'BOOTSTRAP': bootstrap_head(bootstrap_css),
        'BOOT': boot_json,
    }
    template = assets.read_text('index.html')
    body = _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)
    return body.encode('utf-8')
