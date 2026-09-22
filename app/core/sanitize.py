"""HTML-escape user-supplied free text before it reaches storage.

Fields like question/option text and exam titles are returned as-is over
the JSON API; a frontend that renders them as HTML without its own
escaping would be exposed to stored XSS. `html.escape` neutralizes
`<`, `>`, `&`, `"`, `'` at the input boundary so that risk never reaches
the database.
"""

import html


def sanitize_text(value: str) -> str:
    return html.escape(value)
