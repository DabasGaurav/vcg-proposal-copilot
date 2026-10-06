"""Session cost accounting for the generation stages.

The assignment requires a measured per-session cost in tokens and rupees, plus a
projection to 10,000 users. This module turns the per-call records in
``state["model_usage"]`` into both, and -- because the demo runs a LOCAL model --
reports the local cost and the hosted-API equivalent side by side so the
quality / speed / cost trade-off is explicit rather than asserted.

Every rate below is a configurable assumption, not a measurement. Set them from
live pricing before quoting a figure; `assumptions()` prints exactly what was
used so a number can never be presented without its basis.
"""
from __future__ import annotations

import config


def _tok(event: dict, key: str) -> int:
    return int(event.get(key) or 0)


def totals(model_usage: list[dict]) -> dict:
    """Aggregate the raw per-call usage records."""
    calls = list(model_usage or [])
    by_stage: dict[str, dict] = {}
    for e in calls:
        s = by_stage.setdefault(e.get("stage") or "unknown",
                                {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                 "seconds": 0.0})
        s["calls"] += 1
        s["input_tokens"] += _tok(e, "input_tokens")
        s["output_tokens"] += _tok(e, "output_tokens")
        s["seconds"] += float(e.get("duration_seconds") or 0.0)
    return {
        "calls": len(calls),
        "input_tokens": sum(_tok(e, "input_tokens") for e in calls),
        "output_tokens": sum(_tok(e, "output_tokens") for e in calls),
        "seconds": round(sum(float(e.get("duration_seconds") or 0.0) for e in calls), 2),
        "by_stage": by_stage,
        "provider": (calls[0].get("provider") if calls else None),
        "model": (calls[0].get("model") if calls else None),
    }


def session_cost(model_usage: list[dict]) -> dict:
    """Per-session cost, local and hosted-API equivalent, in INR."""
    t = totals(model_usage)

    # Local: no per-token charge. The marginal cost is electricity for the
    # seconds the GPU/NPU was busy.
    kwh = (config.LOCAL_DEVICE_WATTS * t["seconds"]) / 3_600_000.0
    local_inr = kwh * config.ELECTRICITY_INR_PER_KWH

    # Hosted equivalent, at the configured per-million-token rates.
    api_usd = (t["input_tokens"] / 1e6) * config.API_USD_PER_MTOK_INPUT + \
              (t["output_tokens"] / 1e6) * config.API_USD_PER_MTOK_OUTPUT
    api_inr = api_usd * config.USD_INR

    return {
        **t,
        "local_inr": round(local_inr, 4),
        "api_equivalent_usd": round(api_usd, 4),
        "api_equivalent_inr": round(api_inr, 3),
    }


def at_scale(model_usage: list[dict], users: int = 10_000,
             sessions_per_user: int = 1) -> dict:
    """Monthly projection. Local inference does not scale on one laptop -- past a
    small concurrency it needs either hosted inference or dedicated GPU capacity,
    so both are reported."""
    c = session_cost(model_usage)
    sessions = users * sessions_per_user
    gpu_hours = (c["seconds"] * sessions) / 3600.0
    return {
        "users": users,
        "sessions_per_user": sessions_per_user,
        "sessions": sessions,
        "input_tokens": c["input_tokens"] * sessions,
        "output_tokens": c["output_tokens"] * sessions,
        "api_monthly_inr": round(c["api_equivalent_inr"] * sessions, 2),
        "self_hosted_gpu_hours": round(gpu_hours, 1),
        "self_hosted_monthly_inr": round(gpu_hours * config.GPU_INR_PER_HOUR, 2),
    }


def assumptions() -> list[tuple[str, str]]:
    """Every rate behind the numbers above, so a figure is never shown bare."""
    return [
        ("Exchange rate", f"₹{config.USD_INR:.0f} per USD"),
        ("Hosted input rate", f"${config.API_USD_PER_MTOK_INPUT}/M tokens"),
        ("Hosted output rate", f"${config.API_USD_PER_MTOK_OUTPUT}/M tokens"),
        ("Local device draw", f"{config.LOCAL_DEVICE_WATTS} W while generating"),
        ("Electricity", f"₹{config.ELECTRICITY_INR_PER_KWH}/kWh"),
        ("Rented GPU", f"₹{config.GPU_INR_PER_HOUR}/hour"),
        ("Scale basis", "10,000 users × 1 session/month"),
    ]
