import html


def sanitize_text(value: str) -> str:
    return html.escape(value)
