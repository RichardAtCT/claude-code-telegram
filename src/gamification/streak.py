"""Streak tracking logic."""

from datetime import date


class StreakTracker:
    @staticmethod
    def calculate_streak(
        last_date: date | None,
        current_streak: int,
        longest_streak: int,
        today: date | None = None,
    ) -> tuple[int, int]:
        """Calculate updated streak values. Returns (current_streak, longest_streak)."""
        if today is None:
            today = date.today()

        if last_date is None:
            return 1, max(longest_streak, 1)

        delta = (today - last_date).days

        if delta == 0:
            return current_streak, longest_streak
        elif delta == 1:
            new_streak = current_streak + 1
            return new_streak, max(longest_streak, new_streak)
        else:
            return 1, longest_streak
