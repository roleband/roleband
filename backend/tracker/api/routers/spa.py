"""Built dashboard (single-origin) SPA shell + client-route fallback.

Included last so every /api route wins first. Routes register unconditionally
so the route table is identical with or without a built dashboard (the frozen
route-table gate runs on CI, where `dashboard/dist` does not exist); the
handlers check for the build per request and 404 when serving headlessly.
The /assets static mount lives in app.py and serves through `DashboardAssets`.

Every file of the build carries the same policy headers, whatever path reached
it: `/INDEX.HTML` is `index.html` on a case-insensitive filesystem, and a
policy keyed on a file name misses it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from tracker.api.csp import dashboard_csp
from tracker.api.errors import ErrorCode, api_error
from tracker.config import get_settings
from tracker.platform.paths import DASHBOARD_DIST

router = APIRouter()


# The shell must be REVALIDATED on every load, while the hashed bundles it
# points at stay cacheable forever.
#
# Without this the browser applies heuristic freshness to `index.html` and can
# keep serving a shell that references a bundle a rebuild already deleted — the
# page then looks unchanged after a deploy, or 404s its own script.
# `no-cache` is not "do not store": the ETag still makes the common case a 304.
_SHELL_HEADERS = {"Cache-Control": "no-cache"}


def _policy_headers() -> dict[str, str]:
    """What every file of the build is served under. A policy on an image or a
    script is inert, so one set for all is safer than choosing by file type."""
    return {
        "Content-Security-Policy": dashboard_csp(get_settings().usage_stats_host),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


def _serve(path: Path) -> FileResponse:
    return FileResponse(path, headers={**_SHELL_HEADERS, **_policy_headers()})


def _index() -> FileResponse:
    index = DASHBOARD_DIST / "index.html"
    if not index.is_file():
        raise api_error(404, ErrorCode.PAGE_NOT_FOUND, "dashboard build not present")
    return _serve(index)


class DashboardAssets(StaticFiles):
    """The hashed bundles under /assets: the policy headers, and no
    `no-cache`, since a hashed name is its own version."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update(_policy_headers())
        return response


@router.get("/", include_in_schema=False)
async def _spa_root() -> FileResponse:
    return _index()


@router.get("/{full_path:path}", include_in_schema=False)
async def _spa_fallback(full_path: str) -> FileResponse:
    # /api/* never reaches here for known routes; guard unknown ones so a
    # bad API path 404s as JSON-ish rather than silently returning the SPA.
    if full_path.startswith("api/"):
        raise api_error(404, ErrorCode.PAGE_NOT_FOUND, "not found")
    candidate = DASHBOARD_DIST / full_path
    if candidate.is_file() and candidate.resolve().is_relative_to(DASHBOARD_DIST.resolve()):
        return _serve(candidate)
    # Client-side route (e.g. /favorites) -> hand back the SPA shell.
    return _index()
