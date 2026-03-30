"""Tests for the /schedule command handler."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.schedule import schedule_command


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def mock_scheduler():
    scheduler = AsyncMock()
    scheduler.list_jobs = AsyncMock(return_value=[])
    scheduler.add_job = AsyncMock(return_value="job-123")
    scheduler.remove_job = AsyncMock(return_value=True)
    scheduler.pause_job = AsyncMock(return_value=True)
    scheduler.resume_job = AsyncMock(return_value=True)
    return scheduler


@pytest.fixture
def update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user = MagicMock()
    update.effective_user.id = 67890
    return update


@pytest.fixture
def context(mock_scheduler, tmp_dir):
    context = MagicMock()
    context.bot_data = {
        "scheduler": mock_scheduler,
        "settings": MagicMock(approved_directory=tmp_dir),
    }
    context.user_data = {"current_directory": tmp_dir}
    context.args = []
    return context


async def test_no_scheduler_shows_error(update, context):
    """When scheduler is not injected, show error message."""
    context.bot_data["scheduler"] = None
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "not enabled" in update.message.reply_text.call_args[0][0]


async def test_no_args_shows_usage(update, context):
    """No subcommand shows usage info."""
    context.args = []
    await schedule_command(update, context)
    update.message.reply_html.assert_called_once()
    assert "Usage" in update.message.reply_html.call_args[0][0]


async def test_unknown_subcommand_shows_usage(update, context):
    """Unknown subcommand shows usage info."""
    context.args = ["unknown"]
    await schedule_command(update, context)
    update.message.reply_html.assert_called_once()
    assert "Usage" in update.message.reply_html.call_args[0][0]


async def test_list_empty(update, context, mock_scheduler):
    """List with no jobs shows empty message."""
    context.args = ["list"]
    await schedule_command(update, context)
    mock_scheduler.list_jobs.assert_called_once_with(include_paused=True)
    update.message.reply_text.assert_called_once_with("No scheduled jobs.")


async def test_list_with_jobs(update, context, mock_scheduler):
    """List with jobs formats them correctly."""
    mock_scheduler.list_jobs.return_value = [
        {
            "job_id": "abc-123",
            "job_name": "daily-report",
            "cron_expression": "0 9 * * *",
            "is_active": 1,
        },
        {
            "job_id": "def-456",
            "job_name": "weekly-backup",
            "cron_expression": "0 0 * * 0",
            "is_active": 0,
        },
    ]
    context.args = ["list"]
    await schedule_command(update, context)
    html = update.message.reply_html.call_args[0][0]
    assert "daily-report" in html
    assert "active" in html
    assert "weekly-backup" in html
    assert "paused" in html
    assert "abc-123" in html


async def test_add_success(update, context, mock_scheduler, tmp_dir):
    """Add creates a job with correct parameters."""
    context.args = ["add", "my-job", "0", "9", "*", "*", "1-5", "Run", "status", "check"]
    await schedule_command(update, context)

    mock_scheduler.add_job.assert_called_once_with(
        job_name="my-job",
        cron_expression="0 9 * * 1-5",
        prompt="Run status check",
        target_chat_ids=[12345],
        working_directory=tmp_dir,
        created_by=67890,
    )
    html = update.message.reply_html.call_args[0][0]
    assert "my-job" in html
    assert "job-123" in html


async def test_add_too_few_args(update, context):
    """Add with insufficient args shows usage."""
    context.args = ["add", "my-job", "0", "9"]
    await schedule_command(update, context)
    update.message.reply_html.assert_called_once()
    assert "Usage" in update.message.reply_html.call_args[0][0]


async def test_add_failure(update, context, mock_scheduler):
    """Add handles scheduler errors gracefully."""
    mock_scheduler.add_job.side_effect = ValueError("Invalid cron expression")
    context.args = ["add", "bad-job", "x", "y", "z", "a", "b", "Do", "something"]
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "Failed" in update.message.reply_text.call_args[0][0]


async def test_remove(update, context, mock_scheduler):
    """Remove calls scheduler.remove_job."""
    context.args = ["remove", "job-123"]
    await schedule_command(update, context)
    mock_scheduler.remove_job.assert_called_once_with("job-123")
    html = update.message.reply_html.call_args[0][0]
    assert "job-123" in html
    assert "removed" in html


async def test_remove_no_id(update, context):
    """Remove without job_id shows usage."""
    context.args = ["remove"]
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "Usage" in update.message.reply_text.call_args[0][0]


async def test_pause_success(update, context, mock_scheduler):
    """Pause calls scheduler.pause_job."""
    context.args = ["pause", "job-123"]
    await schedule_command(update, context)
    mock_scheduler.pause_job.assert_called_once_with("job-123")
    html = update.message.reply_html.call_args[0][0]
    assert "paused" in html


async def test_pause_not_found(update, context, mock_scheduler):
    """Pause with unknown job_id shows not found."""
    mock_scheduler.pause_job.return_value = False
    context.args = ["pause", "unknown-id"]
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "not found" in update.message.reply_text.call_args[0][0]


async def test_pause_no_id(update, context):
    """Pause without job_id shows usage."""
    context.args = ["pause"]
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "Usage" in update.message.reply_text.call_args[0][0]


async def test_resume_success(update, context, mock_scheduler):
    """Resume calls scheduler.resume_job."""
    context.args = ["resume", "job-123"]
    await schedule_command(update, context)
    mock_scheduler.resume_job.assert_called_once_with("job-123")
    html = update.message.reply_html.call_args[0][0]
    assert "resumed" in html


async def test_resume_not_found(update, context, mock_scheduler):
    """Resume with unknown job_id shows failure message."""
    mock_scheduler.resume_job.return_value = False
    context.args = ["resume", "unknown-id"]
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "not found" in update.message.reply_text.call_args[0][0]


async def test_resume_no_id(update, context):
    """Resume without job_id shows usage."""
    context.args = ["resume"]
    await schedule_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "Usage" in update.message.reply_text.call_args[0][0]
