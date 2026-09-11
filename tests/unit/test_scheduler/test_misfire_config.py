"""Tests for scheduler misfire configuration."""

from unittest.mock import MagicMock

import pytest

from src.events.bus import EventBus
from src.scheduler.scheduler import JobScheduler
from src.storage.database import DatabaseManager


class TestSchedulerMisfireConfig:
    """Verify APScheduler is configured for resilient job execution."""

    @pytest.fixture
    def scheduler(self, tmp_path):
        event_bus = EventBus()
        db_manager = MagicMock(spec=DatabaseManager)
        return JobScheduler(
            event_bus=event_bus,
            db_manager=db_manager,
            default_working_directory=tmp_path,
        )

    def test_misfire_grace_time_is_none(self, scheduler):
        """misfire_grace_time=None ensures jobs always run, no matter how late."""
        job_defaults = scheduler._scheduler._job_defaults
        assert (
            job_defaults.get("misfire_grace_time") is None
        ), "misfire_grace_time must be None to guarantee late jobs still fire"

    def test_coalesce_is_enabled(self, scheduler):
        """coalesce=True merges multiple missed runs into a single execution."""
        job_defaults = scheduler._scheduler._job_defaults
        assert (
            job_defaults.get("coalesce") is True
        ), "coalesce must be True to prevent spam-firing missed runs"
