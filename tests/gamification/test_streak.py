"""Tests for StreakTracker."""

import pytest
from datetime import date

from src.gamification.streak import StreakTracker


class TestStreakUpdate:
    def test_first_activity_starts_streak_at_1(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=None, current_streak=0, longest_streak=0, today=date(2026, 3, 10)
        )
        assert current_streak == 1
        assert longest == 1

    def test_consecutive_day_increments(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 9), current_streak=5, longest_streak=5,
            today=date(2026, 3, 10),
        )
        assert current_streak == 6
        assert longest == 6

    def test_same_day_no_change(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 10), current_streak=5, longest_streak=10,
            today=date(2026, 3, 10),
        )
        assert current_streak == 5
        assert longest == 10

    def test_gap_resets_streak(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 8), current_streak=5, longest_streak=5,
            today=date(2026, 3, 10),
        )
        assert current_streak == 1
        assert longest == 5  # longest preserved

    def test_longest_streak_preserved(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 9), current_streak=3, longest_streak=20,
            today=date(2026, 3, 10),
        )
        assert current_streak == 4
        assert longest == 20
