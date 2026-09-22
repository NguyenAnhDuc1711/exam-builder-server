"""T001 — Fail-fast configuration validation (NFR-3, NFR-4).

Asserts that omitting REDIS_URL or any SMTP_* variable raises ValidationError
at Settings() construction time, before any request can be served.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "var_name",
    [
        "REDIS_URL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_ADDRESS",
    ],
)
def test_missing_required_setting_raises_validation_error(monkeypatch, var_name):
    monkeypatch.delenv(var_name, raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    errors = exc_info.value.errors()
    assert any(err["loc"] == (var_name,) for err in errors)
