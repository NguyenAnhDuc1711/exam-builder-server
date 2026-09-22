"""Rate limiting coverage guard test (T012, AD-2).

Walks `app.routes` and asserts:
1. Every API route (excluding swagger/openapi/health) carries a dependency tagged with `__rate_limit_group__`.
2. Every route maps to its exact expected rate-limit group per the epic mapping table.
"""

import pytest
from fastapi.routing import APIRoute

from app.main import app

_IGNORED_PATHS = {
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/health",
}

_EXPECTED_MAPPING = {
    ("POST", "/auth/login"): "auth",
    ("POST", "/auth/refresh"): "auth",
    ("POST", "/auth/forgot-password"): "auth",
    ("POST", "/auth/verify-otp"): "auth",
    ("POST", "/auth/reset-password"): "auth",
    ("POST", "/users"): "write",
    ("POST", "/questions"): "write",
    ("GET", "/questions"): "read",
    ("POST", "/exams"): "write",
    ("POST", "/exams/{exam_id}/assign"): "write",
    ("GET", "/exams/{exam_id}"): "read",
    ("POST", "/exams/{assignment_id}/submit"): "submit",
    ("GET", "/submissions/{submission_id}"): "read",
    ("GET", "/exams/{exam_id}/submissions"): "read",
}


def _extract_rate_limit_group(route: APIRoute) -> str | None:
    """Extract __rate_limit_group__ from route dependencies or dependant tree."""
    for dep in route.dependencies:
        call = getattr(dep, "dependency", None)
        if hasattr(call, "__rate_limit_group__"):
            return getattr(call, "__rate_limit_group__")

    if hasattr(route, "dependant"):
        for d in route.dependant.dependencies:
            call = getattr(d, "call", None)
            if hasattr(call, "__rate_limit_group__"):
                return getattr(call, "__rate_limit_group__")

    return None


def test_all_routes_have_rate_limiting():
    """Assert every API route is protected by a rate limit dependency."""
    api_routes = [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and r.path not in _IGNORED_PATHS
    ]

    assert len(api_routes) >= 14

    missing_limits = []
    for route in api_routes:
        group = _extract_rate_limit_group(route)
        if group is None:
            missing_limits.append(f"{route.methods} {route.path}")

    assert (
        not missing_limits
    ), f"Routes found without rate limiting dependencies: {missing_limits}"


def test_route_rate_limit_group_mapping():
    """Assert each route is assigned to its exact expected rate limit group."""
    api_routes = [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and r.path not in _IGNORED_PATHS
    ]

    for route in api_routes:
        group = _extract_rate_limit_group(route)
        for method in route.methods:
            if (method, route.path) in _EXPECTED_MAPPING:
                expected_group = _EXPECTED_MAPPING[(method, route.path)]
                assert (
                    group == expected_group
                ), f"Route {method} {route.path} mapped to {group!r}, expected {expected_group!r}"
