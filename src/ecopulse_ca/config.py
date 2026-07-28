"""Project configuration, loaded from .env.

Design note: the fixture/live decision is resolved here, once, rather than being
re-derived at each call site. `ECOPULSE_USE_FIXTURES=auto` means "fixtures until a key
exists" -- so the pipeline and the whole test suite run end-to-end with no credentials,
and flip to live the moment the user pastes a key. Nothing else has to change.

The `fixture` flag propagates into the run log so that no number computed from synthetic
data can ever be mistaken for a finding.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# The five Central Asian states. TM is retained despite having no national monitoring
# (OpenAQ 2024 landscape report) because the US Embassy monitor in Ashgabat is the only
# route to any Turkmen ground truth -- see research/LITERATURE.md A1.
DEFAULT_COUNTRIES = ("UZ", "KZ", "KG", "TJ", "TM")

WHO_2021_PM25_24H = 15.0  # ug/m3, WHO 2021 24-hour guideline
WHO_2021_PM25_ANNUAL = 5.0  # ug/m3, WHO 2021 annual guideline


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _resolve_fixtures(raw: str, has_key: bool) -> bool:
    """Resolve the tri-state ECOPULSE_USE_FIXTURES flag.

    "auto" (the shipped default) means: fixtures until a real key exists. Explicit "1"/"0"
    override, for debugging only.
    """
    raw = raw.lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return not has_key  # "auto"


@dataclass(frozen=True)
class Settings:
    openaq_api_key: str = field(repr=False, default="")
    airnow_api_key: str = field(repr=False, default="")
    use_fixtures: bool = True
    cache_dir: Path = ROOT / "data" / "raw" / "cache"
    countries: tuple[str, ...] = DEFAULT_COUNTRIES

    @classmethod
    def from_env(cls) -> Settings:
        key = _env("OPENAQ_API_KEY")
        countries = _env("ECOPULSE_COUNTRIES") or ",".join(DEFAULT_COUNTRIES)
        cache = _env("ECOPULSE_CACHE_DIR") or "data/raw/cache"
        cache_path = Path(cache)
        return cls(
            openaq_api_key=key,
            airnow_api_key=_env("AIRNOW_API_KEY"),
            use_fixtures=_resolve_fixtures(_env("ECOPULSE_USE_FIXTURES", "auto"), bool(key)),
            cache_dir=cache_path if cache_path.is_absolute() else ROOT / cache_path,
            countries=tuple(c.strip().upper() for c in countries.split(",") if c.strip()),
        )

    @property
    def provenance(self) -> dict[str, object]:
        """Non-secret description of how data was obtained. Safe to log and to commit.

        Never include the key itself -- `openaq_api_key` is repr=False for the same reason.
        """
        return {
            "source": "fixtures" if self.use_fixtures else "live-api",
            "fixture": self.use_fixtures,
            "countries": list(self.countries),
            "has_openaq_key": bool(self.openaq_api_key),
        }


SETTINGS = Settings.from_env()
