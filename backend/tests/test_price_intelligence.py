from datetime import datetime, timedelta, timezone

from app.services.price_intelligence import Observation, compute_stats, evaluate_signal

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def series(prices, step_days=1):
    return [
        Observation(NOW - timedelta(days=(len(prices) - 1 - i) * step_days), p)
        for i, p in enumerate(prices)
    ]


def test_insufficient_data():
    sig = evaluate_signal(compute_stats(series([100, 101, 99]), NOW))
    assert sig.action == "INSUFFICIENT_DATA" and "Not enough BuyWise history" in sig.reasoning
    assert evaluate_signal(None).action == "INSUFFICIENT_DATA"


def test_good_deal_buy_now():
    prices = [30000] * 80 + [25000] * 10
    stats = compute_stats(series(prices), NOW)
    sig = evaluate_signal(stats)
    assert stats.percent_vs_average < -8
    assert sig.status == "GOOD_DEAL" and sig.action == "BUY_NOW"
    assert sig.confidence_level == "high"


def test_high_price_wait():
    prices = [25000] * 80 + [30000] * 10
    sig = evaluate_signal(compute_stats(series(prices), NOW))
    assert sig.status == "HIGH_PRICE" and sig.action == "WAIT" and sig.target_price


def test_average_neutral():
    prices = [25000 + (i % 3) * 100 for i in range(60)]
    sig = evaluate_signal(compute_stats(series(prices), NOW))
    assert sig.status == "AVERAGE_PRICE" and sig.action in ("NEUTRAL", "WAIT")


def test_daily_minimum_collapses_multiple_observations():
    obs = [Observation(NOW, 200), Observation(NOW, 150), Observation(NOW - timedelta(days=1), 180)]
    stats = compute_stats(obs, NOW)
    assert stats.current_price == 150 and stats.observations == 2


def test_stats_windows():
    prices = list(range(100, 190))  # rising
    stats = compute_stats(series(prices), NOW)
    assert stats.average_7d > stats.average_30d > stats.average_90d
    assert stats.historical_low == 100 and stats.historical_high == 189 and stats.trend == "rising"
