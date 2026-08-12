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
class CTFTimeTeamResult:
    place: int
    points: float | None
    team_id: int


def _parse_points(raw: object) -> float | None:
    """CTFTime serializes points as a string (`"6856.0000"`), not a number."""
    if raw is None or raw == "":
        return None
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("Unparseable CTFTime points value: %r", raw)
        return None


def _parse_scores(scores: list[dict]) -> list[CTFTimeTeamResult]:
    parsed = []
    for entry in scores:
        try:
            parsed.append(
                CTFTimeTeamResult(
                    place=int(entry["place"]),
                    points=_parse_points(entry.get("points")),
                    team_id=int(entry["team_id"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping malformed CTFTime standings entry: %r", entry)
    return parsed


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
        response.raise_for_status()
        return [_parse_event(item) for item in response.json()]

    async def get_year_results(self, year: int) -> dict[int, list[CTFTimeTeamResult]]:
        """Standings for every event of `year` that has published results,
        keyed by CTFTime event id.

        There is deliberately no per-event variant: CTFTime's API exposes
        results only per year (`/api/v1/results/<year>/`) — `/events/<id>/
        results/` returns 404 against the live API. One request therefore
        covers every CTF we ran in that year, which is why the sync job
        groups its candidates by year before calling this.
        """
        response = await self._get_with_retries(f"/results/{year}/")
        if response.status_code == 404:
            return {}
        response.raise_for_status()

        results: dict[int, list[CTFTimeTeamResult]] = {}
        for event_id, event in response.json().items():
            try:
                key = int(event_id)
            except (TypeError, ValueError):
                logger.warning("Skipping non-numeric CTFTime event key: %r", event_id)
                continue
            results[key] = _parse_scores(event.get("scores") or [])
        return results

    async def _get_with_retries(
        self, path: str, *, params: dict[str, object] | None = None
    ) -> httpx.Response:
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
