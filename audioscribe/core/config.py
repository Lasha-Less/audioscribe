from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass(frozen=True)
class Settings:
    """
    Minimal core settings.
    Keep this tiny. Extend only when a slice requires it.
    """
    cookies_from_browser: Optional[str] = None


def get_settings() -> Settings:
    """
    Minimal config loader.

    For now we only support an env var override to keep things simple:
      AUDIOSCRIBE_COOKIES_FROM_BROWSER=firefox

    If not set, auth cookies are not used.
    """
    v = os.getenv("AUDIOSCRIBE_COOKIES_FROM_BROWSER")
    v = v.strip() if v else None
    return Settings(cookies_from_browser=v or None)