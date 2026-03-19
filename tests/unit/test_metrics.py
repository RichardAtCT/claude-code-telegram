"""Tests for the metrics collector module."""

import pytest

from src.api.metrics import MetricsCollector


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the MetricsCollector singleton between tests."""
    MetricsCollector.reset()
    yield
    MetricsCollector.reset()


@pytest.fixture
def collector():
    return MetricsCollector()


# ---------------------------------------------------------------------------
# Counter tests
# ---------------------------------------------------------------------------


def test_increment_requests(collector):
    collector.inc_requests()
    collector.inc_requests()
    snap = collector.get_snapshot()
    assert snap["requests_total"] == 2


def test_increment_errors(collector):
    collector.inc_errors()
    snap = collector.get_snapshot()
    assert snap["errors_total"] == 1


def test_add_cost(collector):
    collector.add_cost(user_id=42, cost=1.5)
    collector.add_cost(user_id=42, cost=0.5)
    snap = collector.get_snapshot()
    assert snap["cost_by_user"][42] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Gauge tests
# ---------------------------------------------------------------------------


def test_active_sessions_gauge(collector):
    collector.inc_active_sessions()
    collector.inc_active_sessions()
    snap = collector.get_snapshot()
    assert snap["active_sessions"] == 2

    collector.dec_active_sessions()
    snap = collector.get_snapshot()
    assert snap["active_sessions"] == 1


def test_dec_active_sessions_does_not_go_below_zero(collector):
    collector.dec_active_sessions()
    snap = collector.get_snapshot()
    assert snap["active_sessions"] == 0


# ---------------------------------------------------------------------------
# Histogram tests
# ---------------------------------------------------------------------------


def test_observe_response_time(collector):
    collector.observe_response_time(0.5)
    collector.observe_response_time(2.0)
    snap = collector.get_snapshot()
    assert snap["response_time_count"] == 2
    assert snap["response_time_sum"] == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# Prometheus text format
# ---------------------------------------------------------------------------


def test_render_prometheus_format(collector):
    collector.inc_requests()
    collector.inc_requests()
    collector.inc_errors()
    collector.add_cost(user_id=1, cost=0.5)
    collector.observe_response_time(1.0)

    output = collector.render_prometheus()

    assert "# TYPE telegram_bot_requests_total counter" in output
    assert "telegram_bot_requests_total 2" in output
    assert "# TYPE telegram_bot_errors_total counter" in output
    assert "telegram_bot_errors_total 1" in output
    assert 'telegram_bot_cost_total{user_id="1"}' in output
    assert "telegram_bot_response_time_seconds_bucket" in output
    assert "telegram_bot_response_time_seconds_sum" in output
    assert "telegram_bot_response_time_seconds_count 1" in output


def test_render_prometheus_empty(collector):
    output = collector.render_prometheus()
    assert "telegram_bot_requests_total 0" in output
    assert "telegram_bot_cost_total 0" in output


def test_singleton_behavior():
    a = MetricsCollector()
    b = MetricsCollector()
    assert a is b

    a.inc_requests()
    assert b.get_snapshot()["requests_total"] == 1
