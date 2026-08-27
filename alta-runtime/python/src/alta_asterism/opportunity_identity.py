import hashlib
import json
import re
import unicodedata
from typing import Any


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[_\W]+", "-", normalized).strip("-")


def normalize_catalyst_bucket(value: str | None) -> str:
    """Return the shared portfolio bucket for a possibly legacy catalyst key."""

    normalized = normalize_key(value) if value else ""
    return normalized[:128] or "legacy-unclassified"


def horizon_bucket(horizon_days: int) -> str:
    """Stabilize identity when an agent varies a nearby holding-period estimate."""
    if not 1 <= horizon_days <= 365:
        raise ValueError("Opportunity horizon must be between 1 and 365 days")
    for upper, label in (
        (5, "1-5d"),
        (20, "6-20d"),
        (65, "21-65d"),
        (180, "66-180d"),
        (365, "181-365d"),
    ):
        if horizon_days <= upper:
            return label
    raise AssertionError("validated Opportunity horizon did not match a bucket")


def exact_identity_key(
    entity_key: str | None,
    event_key: str | None,
    direction: str | None,
    horizon_days: int,
) -> str | None:
    if not entity_key or not event_key or direction is None:
        return None
    return canonical_hash(
        {
            "identity_version": 2,
            "entity": normalize_key(entity_key),
            "event": normalize_key(event_key),
            "direction": direction,
            "horizon_bucket": horizon_bucket(horizon_days),
        }
    )


def structural_identity_key(
    entity_key: str | None,
    catalyst_key: str | None,
    direction: str | None,
    horizon_days: int,
) -> str | None:
    if not entity_key or not catalyst_key or direction is None:
        return None
    return canonical_hash(
        {
            "identity_version": 2,
            "entity": normalize_key(entity_key),
            "catalyst": normalize_key(catalyst_key),
            "direction": direction,
            "horizon_bucket": horizon_bucket(horizon_days),
        }
    )
