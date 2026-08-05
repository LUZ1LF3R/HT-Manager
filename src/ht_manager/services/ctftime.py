from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

CTFTIME_BASE_URL = "https://ctftime.org/api/v1"

# CTFTime asks clients to identify themselves and avoid aggressive scraping
# (spec §10) — a generic httpx UA gets blocked by their edge.
DEFAULT_HEADERS = {"User-Agent": "HT-Manager/1.0 (+https://hackertroupe.dev)"}


class CTFTimeError(Exception):
    """Raised when the CTFTime API can't be reached after retries."""


@dataclass(frozen=True)
class CTFTimeEvent:
    ctftime_event_id: int
    name: str
    ctftime_url: str
    official_url: str | None
    start_at: datetime
    end_at: datetime
    weight: float | None


def _parse_event(payload: dict) -> CTFTimeEvent:
    return CTFTimeEvent(
        ctftime_event_id=payload["id"],
        name=payload["title"],
        ctftime_url=payload.get("ctftime_url") or f"https://ctftime.org/event/{payload['id']}",
        official_url=payload.get("url") or None,
        start_at=datetime.fromisoformat(payload["start"]),
        end_at=datetime.fromisoformat(payload["finish"]),
        weight=payload.get("weight"),
    )


class CTFTimeClient:
    """Isolated CTFTime HTTP client (spec §10) — CTFTime's interface/HTML is
    unstable, so all parsing lives behind this one seam. Never called
    directly outside `services/ctftime.py`."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=CTFTIME_BASE_URL, headers=DEFAULT_HEADERS, timeout=timeout
        )
        self._owns_client = client is None
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_event(self, ctftime_event_id: int) -> CTFTimeEvent | None:
        response = await self._get_with_retries(f"/events/{ctftime_event_id}/")
        if response is None:
            return None
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _parse_event(response.json())

    async def list_upcoming_events(
        self, *, start: datetime, finish: datetime, limit: int = 10
    ) -> list[CTFTimeEvent]:
        """Upcoming events in `[start, finish]`, per spec §7.1 step 3 — the
        caller decides the curation window; this only fetches and parses."""
        response = await self._get_with_retries(
            "/events/",
            params={
                "limit": limit,
                "start": int(start.timestamp()),
                "finish": int(finish.timestamp()),
            },
        )
        if response is None:
            return []
        response.raise_for_status()
        return [_parse_event(item) for item in response.json()]

    async def _get_with_retries(
        self, path: str, *, params: dict[str, object] | None = None
    ) -> httpx.Response | None:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "CTFTime request failed (attempt %s/%s): %s", attempt, self._max_retries, exc
                )
            else:
                if response.status_code >= 500:
                    last_error = CTFTimeError(f"CTFTime returned {response.status_code}")
                    logger.warning(
                        "CTFTime returned %s (attempt %s/%s)",
                        response.status_code,
                        attempt,
                        self._max_retries,
                    )
                else:
                    return response

            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff_seconds * attempt)

        raise CTFTimeError(
            f"CTFTime request to {path} failed after {self._max_retries} attempts"
        ) from last_error
