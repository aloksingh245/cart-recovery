"""Reference policy. Persistence, scheduling, and customer locks belong to services."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal
from zoneinfo import ZoneInfo

Channel = Literal["email", "sms"]


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


@dataclass(frozen=True)
class Policy:
    version: str = "recovery-v1"
    abandonment_minutes: int = 60
    cart_expiry_days: int = 14
    attribution_days: int = 7
    email_cap_24h: int = 1
    sms_cap_72h: int = 1
    all_channel_cap_7d: int = 3
    quiet_start_hour: int = 21
    quiet_end_hour: int = 9

    def __post_init__(self):
        if not self.version or min(self.abandonment_minutes, self.cart_expiry_days,
                                   self.attribution_days, self.email_cap_24h,
                                   self.sms_cap_72h, self.all_channel_cap_7d) <= 0:
            raise ValueError("policy windows/caps must be positive")
        if not 0 <= self.quiet_start_hour <= 23 or not 0 <= self.quiet_end_hour <= 23:
            raise ValueError("quiet hours must be in 0..23")


@dataclass(frozen=True)
class Consent:
    channel: Channel
    state: Literal["granted", "withdrawn"]
    effective_at: datetime
    recorded_at: datetime
    revision: int

    def __post_init__(self):
        aware(self.effective_at)
        aware(self.recorded_at)
        if self.channel not in ("email", "sms") or self.state not in ("granted", "withdrawn"):
            raise ValueError("invalid consent enum")
        if self.revision < 1:
            raise ValueError("consent revision must be positive")


@dataclass(frozen=True)
class Contact:
    channel: Channel
    at: datetime

    def __post_init__(self):
        aware(self.at)
        if self.channel not in ("email", "sms"):
            raise ValueError("invalid contact channel")


@dataclass(frozen=True)
class Decision:
    eligible: bool
    reasons: tuple[str, ...]
    policy_version: str


def consent_at(history: list[Consent], channel: Channel, at: datetime) -> bool:
    aware(at)
    known = [c for c in history if c.channel == channel
             and c.effective_at <= at and c.recorded_at <= at]
    if not known:
        return False
    # Same-time withdrawal wins even over a grant received in a later revision.
    latest = max(known, key=lambda c: (c.effective_at, c.state == "withdrawn", c.revision))
    return latest.state == "granted"


def evaluate(*, now: datetime, last_activity: datetime, purchased_at: datetime | None,
             quantity: int, total_minor: int, channel: Channel, timezone: str,
             consent: list[Consent], contacts: list[Contact],
             blocked: bool = False, policy: Policy = Policy()) -> Decision:
    """Inputs must be scoped to ONE verified customer and one cart by the service.

    Contacts include accepted sends and active reservations across ALL their carts.
    The caller must serialize dispatch with a customer row lock.
    """
    aware(now)
    aware(last_activity)
    if purchased_at is not None:
        aware(purchased_at)
    if channel not in ("email", "sms"):
        raise ValueError("invalid channel")
    if quantity < 0 or total_minor < 0:
        raise ValueError("negative cart quantity/total")
    if last_activity > now:
        raise ValueError("activity is in the future")
    reasons = []
    inactive = now - last_activity
    if purchased_at is not None and purchased_at <= now:
        reasons.append("PURCHASED")
    if quantity == 0 or total_minor == 0:
        reasons.append("EMPTY_CART")
    if inactive < timedelta(minutes=policy.abandonment_minutes):
        reasons.append("ACTIVE_CART")
    if inactive >= timedelta(days=policy.cart_expiry_days):
        reasons.append("EXPIRED_CART")
    if blocked:
        reasons.append("CONTACT_BLOCKED")
    if not consent_at(consent, channel, now):
        reasons.append("NO_CONSENT")
    # A contact exactly at the lower boundary has aged out; now is included.
    def count(days: int, selected: Channel | None = None) -> int:
        return sum(now - timedelta(days=days) < c.at <= now
                   and (selected is None or c.channel == selected) for c in contacts)
    days, cap = (1, policy.email_cap_24h) if channel == "email" else (3, policy.sms_cap_72h)
    if count(days, channel) >= cap:
        reasons.append("CHANNEL_CAP")
    if count(7) >= policy.all_channel_cap_7d:
        reasons.append("GLOBAL_CAP")
    hour = now.astimezone(ZoneInfo(timezone)).hour
    start, end = policy.quiet_start_hour, policy.quiet_end_hour
    quiet = (hour >= start or hour < end) if start > end else start <= hour < end
    if quiet:
        reasons.append("QUIET_HOURS")
    return Decision(not reasons, tuple(reasons), policy.version)


@dataclass(frozen=True)
class Touch:
    event_id: str
    send_id: str
    customer_id: str
    cart_id: str
    clicked_at: datetime
    accepted_at: datetime

    def __post_init__(self):
        aware(self.clicked_at)
        aware(self.accepted_at)
        if self.clicked_at < self.accepted_at:
            raise ValueError("click precedes provider acceptance")


def attribute(*, customer_id: str, cart_id: str, ordered_at: datetime,
              touches: list[Touch], policy: Policy = Policy()) -> Touch | None:
    """Last eligible click for the same cart and verified customer; one winner.

    A click strictly precedes purchase; the seven-day lower boundary is inclusive.
    No fallback to delivery or open; those are not evidence of engagement.
    """
    aware(ordered_at)
    eligible = [t for t in touches if t.customer_id == customer_id and t.cart_id == cart_id
                and ordered_at - timedelta(days=policy.attribution_days)
                <= t.clicked_at < ordered_at]
    return max(eligible, key=lambda t: (t.clicked_at, t.event_id, t.send_id), default=None)


def variant(customer_id: str, seed: int = 20261022) -> str:
    """Stable per customer across devices and campaigns; never use Python hash()."""
    return "AB"[int(sha256(f"{seed}:{customer_id}".encode()).hexdigest()[:16], 16) % 2]
