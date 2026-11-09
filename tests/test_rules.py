from datetime import datetime, timedelta, timezone

import pytest
import asyncio
import httpx

from cart_recovery.api import app
from cart_recovery.rules import Consent, Contact, Touch, attribute, consent_at, evaluate, variant

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def grant(state="granted", at=NOW-timedelta(days=10), revision=1):
    return Consent("email", state, at, at, revision)


def decision(**overrides):
    args = dict(now=NOW, last_activity=NOW-timedelta(hours=1), purchased_at=None,
                quantity=2, total_minor=10000, channel="email", timezone="UTC",
                consent=[grant()], contacts=[])
    return evaluate(**(args | overrides))


def test_time_boundary_and_purchase_override():
    assert decision().eligible
    assert "ACTIVE_CART" in decision(last_activity=NOW-timedelta(minutes=59)).reasons
    assert "PURCHASED" in decision(purchased_at=NOW).reasons
    assert "EXPIRED_CART" in decision(last_activity=NOW-timedelta(days=14)).reasons


def test_opt_out_after_schedule_is_honored_and_same_time_withdrawal_wins():
    history = [grant(), grant("withdrawn", NOW, 2), grant("granted", NOW, 3)]
    assert not consent_at(history, "email", NOW)
    assert "NO_CONSENT" in decision(consent=history).reasons
    assert not consent_at([], "sms", NOW)


def test_late_arriving_consent_was_not_known_at_dispatch():
    history = [grant(), Consent("email", "withdrawn", NOW-timedelta(hours=1),
                                NOW+timedelta(hours=1), 2)]
    assert consent_at(history, "email", NOW)
    assert not consent_at(history, "email", NOW+timedelta(hours=2))


def test_caps_span_carts_and_boundary_ages_out():
    assert "CHANNEL_CAP" in decision(contacts=[Contact("email", NOW)]).reasons
    assert decision(contacts=[Contact("email", NOW-timedelta(days=1))]).eligible
    assert "GLOBAL_CAP" in decision(contacts=[Contact("sms", NOW-timedelta(days=i))
                                              for i in (1, 2, 3)]).reasons


def test_quiet_hours_and_empty_cart():
    assert "QUIET_HOURS" in decision(timezone="Asia/Tokyo").reasons  # 21:00
    assert "EMPTY_CART" in decision(quantity=0, total_minor=0).reasons
    assert "CONTACT_BLOCKED" in decision(blocked=True).reasons


def test_attribution_one_winner_seven_day_boundary_and_wrong_identity():
    def touch(eid, at, customer="CUS-000001", cart="CART-2026-000001"):
        return Touch(eid, f"SEND-{eid}", customer, cart, at, at-timedelta(hours=1))
    old = touch("01", NOW-timedelta(days=7))
    wrong = touch("99", NOW-timedelta(seconds=1), customer="CUS-000002")
    wrong_cart = touch("98", NOW-timedelta(seconds=1), cart="CART-2026-000002")
    recent = touch("02", NOW-timedelta(hours=1))
    args = dict(customer_id="CUS-000001", cart_id="CART-2026-000001", ordered_at=NOW)
    assert attribute(**args, touches=[old]) == old
    assert attribute(**args, touches=[old, recent, wrong, wrong_cart]) == recent
    assert attribute(**args, touches=[touch("03", NOW-timedelta(days=7, seconds=1))]) is None
    assert attribute(**args, touches=[touch("04", NOW)]) is None
    tied = touch("05", recent.clicked_at)
    assert attribute(**args, touches=[tied, recent]) == tied


def test_reject_naive_timestamps_and_negative_money():
    with pytest.raises(ValueError):
        decision(now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        decision(total_minor=-1)
    with pytest.raises(ValueError):
        decision(last_activity=NOW+timedelta(seconds=1))


def test_customer_variant_and_api_contract(monkeypatch):
    assert variant("CUS-000001") == variant("CUS-000001")
    assert {variant(f"CUS-{i:06}") for i in range(100)} == {"A", "B"}
    monkeypatch.delenv("DATABASE_URL", raising=False)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
            assert (await client.get("/healthz")).json()["stage"] == "application"
            assert (await client.get("/readyz")).status_code == 503
            assert (await client.get("/api/policy")).json()["attribution_days"] == 7
    asyncio.run(check())
