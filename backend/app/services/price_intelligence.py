"""Price history statistics and the Buy/Wait engine.

Works only on real observations passed in. If there is not enough history, it
says so instead of guessing. Pure functions — persistence lives in price_history_service.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

MIN_OBSERVATIONS = 7
MIN_SPAN_DAYS = 7


@dataclass
class Observation:
    observed_at: datetime
    price: float


@dataclass
class PriceStats:
    current_price: float
    observations: int
    span_days: int
    average_7d: float | None = None
    average_30d: float | None = None
    average_90d: float | None = None
    historical_low: float | None = None
    historical_high: float | None = None
    percent_vs_average: float | None = None
    percent_vs_low: float | None = None
    trend: str = "unknown"  # rising | falling | stable | unknown
    volatility: float | None = None  # coefficient of variation

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PriceSignal:
    action: str  # BUY_NOW | WAIT | NEUTRAL | INSUFFICIENT_DATA
    status: str  # GOOD_DEAL | AVERAGE_PRICE | HIGH_PRICE | UNKNOWN
    confidence: float
    confidence_level: str
    reasoning: str
    target_price: float | None = None
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def daily_minimums(observations: list[Observation]) -> list[Observation]:
    """Collapse to one point per day: the lowest estimated final price seen that day."""
    by_day: dict[str, Observation] = {}
    for obs in observations:
        key = obs.observed_at.astimezone(timezone.utc).date().isoformat()
        if key not in by_day or obs.price < by_day[key].price:
            by_day[key] = Observation(obs.observed_at, obs.price)
    return sorted(by_day.values(), key=lambda o: o.observed_at)


def _avg_window(series: list[Observation], days: int, now: datetime) -> float | None:
    cutoff = now - timedelta(days=days)
    vals = [o.price for o in series if o.observed_at >= cutoff]
    return round(statistics.mean(vals), 2) if vals else None


def compute_stats(
    observations: list[Observation], now: datetime | None = None
) -> PriceStats | None:
    if not observations:
        return None
    now = now or datetime.now(timezone.utc)
    series = daily_minimums(observations)
    prices = [o.price for o in series]
    current = prices[-1]
    span = (series[-1].observed_at - series[0].observed_at).days
    stats = PriceStats(current_price=current, observations=len(series), span_days=span)
    stats.historical_low = min(prices)
    stats.historical_high = max(prices)
    stats.average_7d = _avg_window(series, 7, now)
    stats.average_30d = _avg_window(series, 30, now)
    stats.average_90d = _avg_window(series, 90, now)
    reference_avg = stats.average_90d or stats.average_30d or stats.average_7d
    if reference_avg:
        stats.percent_vs_average = round((current - reference_avg) / reference_avg * 100, 1)
    if stats.historical_low:
        stats.percent_vs_low = round(
            (current - stats.historical_low) / stats.historical_low * 100, 1
        )
    if len(prices) >= 3:
        stats.volatility = round(statistics.pstdev(prices) / statistics.mean(prices), 4)
    if len(series) >= 6:
        recent = [o.price for o in series if o.observed_at >= now - timedelta(days=7)] or prices[
            -3:
        ]
        earlier = [
            o.price
            for o in series
            if now - timedelta(days=14) <= o.observed_at < now - timedelta(days=7)
        ] or prices[-6:-3]
        if recent and earlier:
            change = (
                (statistics.mean(recent) - statistics.mean(earlier))
                / statistics.mean(earlier)
                * 100
            )
            stats.trend = "rising" if change > 2.5 else "falling" if change < -2.5 else "stable"
    return stats


def evaluate_signal(stats: PriceStats | None, offers_count: int = 0) -> PriceSignal:
    if stats is None or stats.observations < MIN_OBSERVATIONS or stats.span_days < MIN_SPAN_DAYS:
        have = (
            f"{stats.observations} observation(s) over {stats.span_days} day(s)"
            if stats
            else "no observations"
        )
        return PriceSignal(
            action="INSUFFICIENT_DATA",
            status="UNKNOWN",
            confidence=0.0,
            confidence_level="low",
            reasoning=f"Not enough BuyWise history yet ({have}). We need at least {MIN_OBSERVATIONS} daily observations over {MIN_SPAN_DAYS} days before giving a buy/wait signal.",
        )
    pct_avg = stats.percent_vs_average or 0.0
    pct_low = stats.percent_vs_low or 0.0
    evidence: list[str] = []
    window = (
        "90-day"
        if stats.average_90d and stats.span_days >= 60
        else "30-day"
        if stats.average_30d and stats.span_days >= 20
        else "recent"
    )
    evidence.append(
        f"Current price is {abs(pct_avg):.0f}% {'below' if pct_avg < 0 else 'above'} its {window} average."
    )
    evidence.append(
        f"It is {pct_low:.0f}% above the lowest price BuyWise has recorded."
        if pct_low > 0.5
        else "It matches the lowest price BuyWise has recorded."
    )
    if stats.trend != "unknown":
        evidence.append(f"Recent trend: {stats.trend}.")

    # data-quality confidence
    conf = 0.35 + min(stats.observations, 60) / 60 * 0.4 + min(stats.span_days, 90) / 90 * 0.2
    if stats.volatility and stats.volatility > 0.08:
        conf -= 0.1
        evidence.append("Prices for this product are volatile, which lowers confidence.")
    conf = round(max(0.2, min(0.95, conf)), 2)
    level = "high" if conf >= 0.75 else "medium" if conf >= 0.5 else "low"

    if pct_avg <= -8 or (pct_low <= 2 and pct_avg <= -3):
        status = "GOOD_DEAL"
    elif pct_avg >= 8:
        status = "HIGH_PRICE"
    else:
        status = "AVERAGE_PRICE"

    if status == "GOOD_DEAL" and stats.trend != "falling":
        action = "BUY_NOW"
        reasoning = f"Price is {abs(pct_avg):.0f}% below its {window} average" + (
            " and at its recorded low." if pct_low <= 2 else "."
        )
        target = None
    elif status == "GOOD_DEAL" and stats.trend == "falling":
        action = "BUY_NOW"
        reasoning = f"Price is already {abs(pct_avg):.0f}% below its {window} average; prices are still drifting down but this is a good price."
        target = None
    elif status == "HIGH_PRICE":
        action = "WAIT"
        reasoning = f"Price is {pct_avg:.0f}% above its {window} average. Historically it has been available for less."
        target = round((stats.average_90d or stats.average_30d or stats.current_price), -1)
    elif stats.trend == "falling":
        action = "WAIT"
        reasoning = "Price is near its average and trending down; waiting a few days may help."
        target = round(stats.historical_low, -1) if stats.historical_low else None
    else:
        action = "NEUTRAL"
        reasoning = f"Price is close to its {window} average. This is a fair price rather than a standout deal."
        target = round(stats.historical_low, -1) if stats.historical_low else None
    return PriceSignal(
        action=action,
        status=status,
        confidence=conf,
        confidence_level=level,
        reasoning=reasoning,
        target_price=target,
        evidence=evidence,
    )
