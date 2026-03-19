"""
Integration Tests: API Key Spending Limit Enforcement

Verifies that daily/weekly/monthly cost limits are enforced at request time:
- Requests are rejected (401, spending_limit_exceeded) when the limit is reached
- Requests pass through when under the limit
- Keys without limits are never blocked
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db, require_admin_auth
from app.common.time import utc_now
from app.db.models import ApiKey as ApiKeyORM
from app.db.models import RequestLog as RequestLogORM
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


async def _create_key(ac: AsyncClient, name: str) -> dict:
    resp = await ac.post("/api/admin/api-keys", json={"key_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_limits(
    ac: AsyncClient,
    key_id: int,
    *,
    daily: float | None = None,
    weekly: float | None = None,
    monthly: float | None = None,
) -> None:
    payload = {}
    if daily is not None:
        payload["daily_cost_limit"] = daily
    if weekly is not None:
        payload["weekly_cost_limit"] = weekly
    if monthly is not None:
        payload["monthly_cost_limit"] = monthly
    resp = await ac.put(f"/api/admin/api-keys/{key_id}", json=payload)
    assert resp.status_code == 200, resp.text


async def _insert_log(db_session, api_key_id: int, cost: float, request_time: datetime) -> None:
    """Insert a minimal request log to simulate prior spending."""
    log = RequestLogORM(
        request_time=_utc_naive(request_time),
        api_key_id=api_key_id,
        api_key_name="test",
        total_cost=cost,
    )
    db_session.add(log)
    await db_session.commit()


async def _proxy_request(ac: AsyncClient, key_value: str) -> int:
    """Hit the /v1/models endpoint (authenticated but no proxy needed) and return status."""
    with patch(
        "app.services.proxy_service.ProxyService.process_request",
        new_callable=AsyncMock,
    ):
        resp = await ac.get(
            "/v1/models",
            headers={"x-api-key": key_value},
        )
    return resp.status_code, resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_limit_never_blocked(db_session):
    """Key without any limits should always pass through."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "no-limit-key")
        key_value = key["key_value"]
        key_id = key["id"]

        # Insert heavy spending — should not matter
        now = utc_now()
        await _insert_log(db_session, key_id, 999.0, now)

        status, body = await _proxy_request(ac, key_value)
        # 200 from /v1/models (no proxy service mock needed for this endpoint)
        assert status == 200, body

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_daily_limit_blocks_when_exceeded(db_session):
    """Request is rejected when today's spending >= daily_cost_limit."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "daily-limit-key")
        key_value = key["key_value"]
        key_id = key["id"]

        await _set_limits(ac, key_id, daily=1.0)

        now = utc_now()
        # Insert cost equal to the limit
        await _insert_log(db_session, key_id, 1.0, now)

        status, body = await _proxy_request(ac, key_value)
        assert status == 401, body
        assert body["error"]["code"] == "spending_limit_exceeded"
        assert "[LLM-Gateway]" in body["error"]["message"]
        assert "Daily" in body["error"]["message"]

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_daily_limit_passes_when_under(db_session):
    """Request passes when today's spending is below daily_cost_limit."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "daily-limit-under-key")
        key_value = key["key_value"]
        key_id = key["id"]

        await _set_limits(ac, key_id, daily=10.0)

        now = utc_now()
        await _insert_log(db_session, key_id, 5.0, now)

        status, body = await _proxy_request(ac, key_value)
        assert status == 200, body

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_weekly_limit_blocks_when_exceeded(db_session):
    """Request is rejected when this week's spending >= weekly_cost_limit."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "weekly-limit-key")
        key_value = key["key_value"]
        key_id = key["id"]

        await _set_limits(ac, key_id, weekly=5.0)

        now = utc_now()
        await _insert_log(db_session, key_id, 5.0, now)

        status, body = await _proxy_request(ac, key_value)
        assert status == 401, body
        assert body["error"]["code"] == "spending_limit_exceeded"
        assert "[LLM-Gateway]" in body["error"]["message"]
        assert "Weekly" in body["error"]["message"]

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_monthly_limit_blocks_when_exceeded(db_session):
    """Request is rejected when this month's spending >= monthly_cost_limit."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "monthly-limit-key")
        key_value = key["key_value"]
        key_id = key["id"]

        await _set_limits(ac, key_id, monthly=2.0)

        now = utc_now()
        await _insert_log(db_session, key_id, 2.5, now)

        status, body = await _proxy_request(ac, key_value)
        assert status == 401, body
        assert body["error"]["code"] == "spending_limit_exceeded"
        assert "[LLM-Gateway]" in body["error"]["message"]
        assert "Monthly" in body["error"]["message"]

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_old_logs_outside_period_not_counted(db_session):
    """Logs from a previous month should not count toward the daily limit."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "old-logs-key")
        key_value = key["key_value"]
        key_id = key["id"]

        await _set_limits(ac, key_id, daily=1.0)

        # Insert a large cost but 40 days ago — outside the monthly window
        old_time = utc_now().replace(day=1) - __import__("datetime").timedelta(days=40)
        await _insert_log(db_session, key_id, 999.0, old_time)

        status, body = await _proxy_request(ac, key_value)
        assert status == 200, body

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_list_endpoint_returns_period_costs_and_limits(db_session):
    """Admin list endpoint returns daily/weekly/monthly costs and limit fields."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_auth] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        key = await _create_key(ac, "list-check-key")
        key_id = key["id"]

        await _set_limits(ac, key_id, daily=1.0, weekly=5.0, monthly=20.0)

        now = utc_now()
        await _insert_log(db_session, key_id, 0.5, now)

        resp = await ac.get("/api/admin/api-keys")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        item = next((i for i in items if i["id"] == key_id), None)
        assert item is not None

        assert item["daily_cost"] == pytest.approx(0.5, abs=1e-6)
        assert item["weekly_cost"] == pytest.approx(0.5, abs=1e-6)
        assert item["monthly_cost"] == pytest.approx(0.5, abs=1e-6)
        assert item["daily_cost_limit"] == pytest.approx(1.0, abs=1e-6)
        assert item["weekly_cost_limit"] == pytest.approx(5.0, abs=1e-6)
        assert item["monthly_cost_limit"] == pytest.approx(20.0, abs=1e-6)

    app.dependency_overrides = {}
