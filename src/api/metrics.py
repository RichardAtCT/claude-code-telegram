"""Prometheus-compatible metrics collector.

Simple in-memory counters and gauges exposed in Prometheus text format.
No external dependencies (no prometheus_client required).
"""

import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


class MetricsCollector:
    """Singleton metrics collector with Prometheus-compatible text output.

    Thread-safe via a single lock. All metric mutations acquire the lock.
    """

    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._mu = threading.Lock()

        # Counters
        self._requests_total: int = 0
        self._errors_total: int = 0
        self._cost_by_user: Dict[int, float] = defaultdict(float)

        # Gauge
        self._active_sessions: int = 0

        # Histogram (response time in seconds)
        self._response_time_buckets: Dict[float, int] = {}
        self._response_time_sum: float = 0.0
        self._response_time_count: int = 0

        # Default Prometheus histogram buckets
        self._bucket_boundaries: List[float] = [
            0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0,
        ]
        for b in self._bucket_boundaries:
            self._response_time_buckets[b] = 0

    # --- Mutation methods ---

    def inc_requests(self) -> None:
        """Increment total request counter."""
        with self._mu:
            self._requests_total += 1

    def inc_errors(self) -> None:
        """Increment total error counter."""
        with self._mu:
            self._errors_total += 1

    def add_cost(self, user_id: int, cost: float) -> None:
        """Add cost for a specific user.

        Caps the number of tracked users to prevent unbounded memory growth.
        """
        with self._mu:
            if user_id not in self._cost_by_user and len(self._cost_by_user) >= 10000:
                # Safety cap: don't track more than 10k unique users in metrics
                return
            self._cost_by_user[user_id] += cost

    def set_active_sessions(self, count: int) -> None:
        """Set the current active session gauge."""
        with self._mu:
            self._active_sessions = count

    def inc_active_sessions(self) -> None:
        with self._mu:
            self._active_sessions += 1

    def dec_active_sessions(self) -> None:
        with self._mu:
            self._active_sessions = max(0, self._active_sessions - 1)

    def observe_response_time(self, seconds: float) -> None:
        """Record a response time observation into histogram buckets."""
        with self._mu:
            self._response_time_sum += seconds
            self._response_time_count += 1
            for b in self._bucket_boundaries:
                if seconds <= b:
                    self._response_time_buckets[b] += 1

    # --- Query methods ---

    def get_snapshot(self) -> Dict:
        """Return a snapshot of all metrics (for testing / introspection)."""
        with self._mu:
            return {
                "requests_total": self._requests_total,
                "errors_total": self._errors_total,
                "active_sessions": self._active_sessions,
                "cost_by_user": dict(self._cost_by_user),
                "response_time_count": self._response_time_count,
                "response_time_sum": self._response_time_sum,
            }

    # --- Prometheus text format ---

    def render_prometheus(self) -> str:
        """Render all metrics in Prometheus exposition text format."""
        with self._mu:
            lines: List[str] = []

            # telegram_bot_requests_total
            lines.append(
                "# HELP telegram_bot_requests_total "
                "Total number of bot requests."
            )
            lines.append("# TYPE telegram_bot_requests_total counter")
            lines.append(f"telegram_bot_requests_total {self._requests_total}")

            # telegram_bot_active_sessions
            lines.append(
                "# HELP telegram_bot_active_sessions "
                "Number of currently active sessions."
            )
            lines.append("# TYPE telegram_bot_active_sessions gauge")
            lines.append(
                f"telegram_bot_active_sessions {self._active_sessions}"
            )

            # telegram_bot_cost_total (per user)
            lines.append(
                "# HELP telegram_bot_cost_total "
                "Total cost incurred, by user."
            )
            lines.append("# TYPE telegram_bot_cost_total counter")
            if self._cost_by_user:
                for user_id, cost in sorted(self._cost_by_user.items()):
                    lines.append(
                        f'telegram_bot_cost_total{{user_id="{user_id}"}} {cost:.6f}'
                    )
            else:
                lines.append("telegram_bot_cost_total 0")

            # telegram_bot_errors_total
            lines.append(
                "# HELP telegram_bot_errors_total "
                "Total number of errors."
            )
            lines.append("# TYPE telegram_bot_errors_total counter")
            lines.append(f"telegram_bot_errors_total {self._errors_total}")

            # telegram_bot_response_time_seconds (histogram)
            lines.append(
                "# HELP telegram_bot_response_time_seconds "
                "Response time distribution in seconds."
            )
            lines.append(
                "# TYPE telegram_bot_response_time_seconds histogram"
            )
            cumulative = 0
            for b in self._bucket_boundaries:
                cumulative += self._response_time_buckets[b]
                lines.append(
                    f'telegram_bot_response_time_seconds_bucket{{le="{b}"}} '
                    f"{cumulative}"
                )
            lines.append(
                f'telegram_bot_response_time_seconds_bucket{{le="+Inf"}} '
                f"{self._response_time_count}"
            )
            lines.append(
                f"telegram_bot_response_time_seconds_sum "
                f"{self._response_time_sum:.6f}"
            )
            lines.append(
                f"telegram_bot_response_time_seconds_count "
                f"{self._response_time_count}"
            )

            return "\n".join(lines) + "\n"

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing only)."""
        with cls._lock:
            cls._instance = None
