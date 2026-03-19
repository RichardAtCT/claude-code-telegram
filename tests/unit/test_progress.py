"""Tests for the progress tracking module."""

import time

import pytest

from src.bot.utils.progress import ProgressTracker, Stage


@pytest.fixture
def tracker():
    return ProgressTracker(start_time=time.time())


def test_initial_stage(tracker):
    assert tracker.current_stage == Stage.INITIALIZING


def test_update_stage_analyzing(tracker):
    stage, emoji, label = tracker.update_stage("Read")
    assert stage == Stage.ANALYZING
    assert tracker.current_stage == Stage.ANALYZING


def test_update_stage_coding(tracker):
    stage, emoji, label = tracker.update_stage("Write")
    assert stage == Stage.CODING


def test_update_stage_testing_with_bash(tracker):
    stage, emoji, label = tracker.update_stage("Bash", {"command": "pytest tests/"})
    assert stage == Stage.TESTING


def test_bash_after_coding_transitions_to_reviewing(tracker):
    tracker.update_stage("Edit")
    assert tracker.current_stage == Stage.CODING

    stage, emoji, label = tracker.update_stage("Bash", {"command": "ls -la"})
    assert stage == Stage.REVIEWING


def test_task_from_initializing_goes_to_analyzing(tracker):
    stage, _, _ = tracker.update_stage("Task")
    assert stage == Stage.ANALYZING


def test_format_progress_english(tracker):
    tracker.update_stage("Grep")
    result = tracker.format_progress(lang="en")
    assert "Analyzing code..." in result
    assert "s)" in result


def test_format_progress_chinese(tracker):
    tracker.update_stage("Write")
    result = tracker.format_progress(lang="zh")
    assert "\u7de8\u5beb\u4ee3\u78bc\u4e2d..." in result


def test_multiple_tool_stage_transitions(tracker):
    tracker.update_stage("Glob")
    assert tracker.current_stage == Stage.ANALYZING

    tracker.update_stage("Edit")
    assert tracker.current_stage == Stage.CODING

    tracker.update_stage("Bash", {"command": "npm test"})
    assert tracker.current_stage == Stage.TESTING
