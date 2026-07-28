"""Shared HTTP plumbing for ingestion clients: retry, disk cache, fixture routing.

Two things here are load-bearing for reproducibility rather than for convenience:

1. **Every live response is cached to disk and checksummed.** `data/MANIFEST.md` requires a
   checksum per source; that is only honest if the bytes that produced a result are the
   bytes on disk. The cache is the archive, not an optimisation.

2. **Fixtures and live responses go through the identical parsing path.** If fixtures took
   a shortcut, the test suite would validate code that never runs in production.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class IngestError(RuntimeError):
    """Raised when a source cannot be retrieved and retrying will not help."""


def cache_key(url: str, params: dict[str, Any] | None) -> str:
    """Stable hash of a request, used as both cache filename and provenance id."""
    payload = json.dumps({"url": url, "params": params or {}}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def sha256_of(obj: Any) -> str:
    """Checksum of a parsed payload, for the data manifest."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def load_fixture(name: str) -> Any:
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        raise IngestError(
            f"fixture {name!r} not found at {path}. Fixtures are committed to the repo so "
            f"the suite runs without credentials; if this is missing, the repo is incomplete."
        )
    return json.loads(path.read_text(encoding="utf-8"))


class HttpSource:
    """Base for HTTP-backed sources.

    Subclasses supply `base_url` and `auth_headers`; this class owns retry, caching, and
    the fixture switch so that behaviour is identical across sources.
    """

    base_url: str = ""
    #: Requests-per-page ceiling the upstream API enforces.
    page_limit: int = 1000

    def __init__(self, *, use_fixtures: bool, cache_dir: Path, timeout: float = 30.0) -> None:
        self.use_fixtures = use_fixtures
        self.cache_dir = cache_dir
        self.timeout = timeout
        self._client: httpx.Client | None = None

    # -- to be provided by subclasses ---------------------------------------------------
    def auth_headers(self) -> dict[str, str]:
        return {}

    def fixture_name(self, path: str, params: dict[str, Any] | None) -> str:
        raise NotImplementedError

    # -- plumbing -----------------------------------------------------------------------
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Accept": "application/json", **self.auth_headers()},
                timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> HttpSource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get_live(self, path: str, params: dict[str, Any]) -> Any:
        resp = self.client.get(path, params=params)
        # 4xx other than 429 will not be fixed by retrying -- fail fast with a clear message.
        if resp.status_code == 401:
            raise IngestError(
                "401 Unauthorized from the API. Check OPENAQ_API_KEY in .env -- it should be "
                "the raw key with no quotes and no surrounding spaces."
            )
        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            raise IngestError(f"{resp.status_code} from {path}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch one page, from fixtures or live, caching live responses to disk."""
        params = params or {}
        if self.use_fixtures:
            return load_fixture(self.fixture_name(path, params))

        key = cache_key(path, params)
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            log.debug("cache hit %s", key)
            return json.loads(cached.read_text(encoding="utf-8"))

        payload = self._get_live(path, params)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Walk every page of a paginated endpoint.

        `meta.found` is not trusted as a stopping condition: OpenAQ returns it as a string
        such as ">1000" when the true count is unknown. Termination is driven by short
        pages instead, which is correct regardless of how `found` is expressed.
        """
        params = dict(params or {})
        params.setdefault("limit", self.page_limit)
        page, out = 1, []
        while True:
            params["page"] = page
            payload = self.get(path, params)
            results = payload.get("results") or []
            out.extend(results)
            if len(results) < int(params["limit"]) or self.use_fixtures:
                break
            page += 1
            if page > 1000:  # pathological-loop guard
                raise IngestError(f"pagination exceeded 1000 pages on {path}")
        return out
