from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from ht_manager.services.ctftime import CTFTimeClient, CTFTimeError

EVENT_PAYLOAD = {
    "id": 42,
    "title": "L3akCTF 2026",
    "ctftime_url": "https://ctftime.org/event/42",
    "url": "https://l3ak.example/",
    "start": "2026-09-01T18:00:00+00:00",
    "finish": "2026-09-03T18:00:00+00:00",
    "weight": 50.0,
}


def _client(handler) -> CTFTimeClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://ctftime.org/api/v1")
    return CTFTimeClient(http_client)


async def test_get_event_parses_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/events/42/"
        return httpx.Response(200, json=EVENT_PAYLOAD)

    client = _client(handler)
    event = await client.get_event(42)
    assert event is not None
    assert event.ctftime_event_id == 42
    assert event.name == "L3akCTF 2026"
    assert event.weight == 50.0


async def test_get_event_returns_none_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(handler)
    assert await client.get_event(999) is None


async def test_get_event_retries_then_raises_on_persistent_5xx() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    client = CTFTimeClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://ctftime.org/api/v1"),
        max_retries=2,
        backoff_seconds=0,
    )
    with pytest.raises(CTFTimeError):
        await client.get_event(1)
    assert attempts == 2


async def test_get_year_results_parses_live_payload_shape() -> None:
    """Mirrors the real `/api/v1/results/<year>/` response: keyed by event id
    as a *string*, standings under `scores`, and `points` serialized as a
    string like "6856.0000" rather than a number."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/results/2026/"
        return httpx.Response(
            200,
            json={
                "42": {
                    "title": "L3akCTF 2026",
                    "scores": [
                        {"team_id": 5, "points": "6856.0000", "place": 1},
                        {"team_id": 999, "points": "5415.0000", "place": 2},
                    ],
                },
                "43": {"title": "Other CTF", "scores": []},
            },
        )

    client = _client(handler)
    results = await client.get_year_results(2026)

    assert set(results) == {42, 43}
    assert results[43] == []
    standings = results[42]
    assert len(standings) == 2
    assert standings[1].team_id == 999
    assert standings[1].place == 2
    assert standings[1].points == 5415.0


async def test_get_year_results_skips_malformed_entries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "42": {
                    "scores": [
                        {"team_id": 5, "points": "100.0", "place": 1},
                        {"team_id": 6, "place": 2},  # missing points -> None, still kept
                        {"points": "50.0", "place": 3},  # no team_id -> dropped
                    ]
                },
                "not-an-id": {"scores": []},
            },
        )

    client = _client(handler)
    results = await client.get_year_results(2026)

    assert set(results) == {42}
    assert [entry.team_id for entry in results[42]] == [5, 6]
    assert results[42][1].points is None


async def test_get_year_results_returns_empty_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(handler)
    assert await client.get_year_results(1999) == {}


async def test_list_upcoming_events_parses_all_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/events/"
        assert request.url.params["limit"] == "5"
        return httpx.Response(200, json=[EVENT_PAYLOAD])

    client = _client(handler)
    events = await client.list_upcoming_events(
        start=datetime(2026, 1, 1, tzinfo=UTC), finish=datetime(2026, 12, 31, tzinfo=UTC), limit=5
    )
    assert len(events) == 1
    assert events[0].ctftime_event_id == 42


async def test_get_event_recovers_after_transient_failure() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=EVENT_PAYLOAD)

    client = CTFTimeClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://ctftime.org/api/v1"),
        max_retries=3,
        backoff_seconds=0,
    )
    event = await client.get_event(42)
    assert event is not None
    assert attempts == 2
