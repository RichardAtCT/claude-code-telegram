"""Tests for the webhook noise filter and stats."""

from typing import Any, Dict

import pytest

from src.events.middleware import (
    DEFAULT_DROP_EVENTS,
    SUCCESS_CONCLUSIONS,
    WebhookFilter,
    WebhookStats,
)


def _wr(action: str, conclusion: str = None) -> Dict[str, Any]:
    """Build a workflow_run-shaped payload."""
    return {
        "action": action,
        "workflow_run": {
            "name": "ci",
            "status": "completed" if action == "completed" else "in_progress",
            "conclusion": conclusion,
            "head_sha": "deadbeef",
            "head_branch": "main",
            "html_url": "https://gh/run/1",
        },
        "repository": {"full_name": "aphrollo/test"},
    }


class TestWebhookFilterDefaults:
    def test_defaults_contain_documented_noise_keys(self) -> None:
        # The documented noise classes appear in DEFAULT_DROP_EVENTS.
        for key in (
            "ping",
            "workflow_run.queued",
            "workflow_run.in_progress",
            "push.deleted",
            "push.created",
        ):
            assert key in DEFAULT_DROP_EVENTS

    def test_ping_dropped(self) -> None:
        f = WebhookFilter()
        escalate, reason = f.should_escalate("ping", {})
        assert escalate is False
        assert reason == "ping"

    def test_workflow_run_queued_dropped(self) -> None:
        f = WebhookFilter()
        escalate, reason = f.should_escalate("workflow_run", _wr("queued"))
        assert escalate is False
        assert reason == "workflow_run.queued"

    def test_workflow_run_in_progress_dropped(self) -> None:
        f = WebhookFilter()
        escalate, _ = f.should_escalate("workflow_run", _wr("in_progress"))
        assert escalate is False

    def test_workflow_run_completed_success_dropped(self) -> None:
        f = WebhookFilter()
        escalate, reason = f.should_escalate(
            "workflow_run", _wr("completed", "success")
        )
        assert escalate is False
        assert reason == "workflow_run.completed.success"

    def test_workflow_run_completed_failure_escalates(self) -> None:
        f = WebhookFilter()
        escalate, reason = f.should_escalate(
            "workflow_run", _wr("completed", "failure")
        )
        assert escalate is True
        assert reason == "escalated"

    @pytest.mark.parametrize(
        "conclusion", ["timed_out", "cancelled", "action_required"]
    )
    def test_workflow_run_completed_anomalies_escalate(self, conclusion: str) -> None:
        f = WebhookFilter()
        escalate, _ = f.should_escalate("workflow_run", _wr("completed", conclusion))
        assert escalate is True

    @pytest.mark.parametrize("conclusion", list(SUCCESS_CONCLUSIONS))
    def test_all_success_like_conclusions_dropped(self, conclusion: str) -> None:
        f = WebhookFilter()
        escalate, _ = f.should_escalate("workflow_run", _wr("completed", conclusion))
        assert escalate is False

    def test_push_branch_delete_dropped(self) -> None:
        f = WebhookFilter()
        escalate, reason = f.should_escalate(
            "push", {"deleted": True, "ref": "refs/heads/feat/x"}
        )
        assert escalate is False
        assert reason == "push.deleted"

    def test_push_branch_create_dropped(self) -> None:
        f = WebhookFilter()
        escalate, reason = f.should_escalate(
            "push", {"created": True, "ref": "refs/heads/feat/x"}
        )
        assert escalate is False
        assert reason == "push.created"

    def test_normal_push_escalates(self) -> None:
        f = WebhookFilter()
        escalate, _ = f.should_escalate(
            "push",
            {
                "ref": "refs/heads/main",
                "before": "aaa",
                "after": "bbb",
                "commits": [{"id": "bbb", "message": "fix"}],
            },
        )
        assert escalate is True

    def test_unknown_event_escalates(self) -> None:
        """Default-pass: unrecognized events still wake the agent."""
        f = WebhookFilter()
        escalate, reason = f.should_escalate("brand_new_event", {"foo": "bar"})
        assert escalate is True
        assert reason == "escalated"


class TestWebhookFilterDedupe:
    def test_duplicate_within_window_dropped(self) -> None:
        f = WebhookFilter()
        # First time through: this would be escalate, but we need a payload
        # that escalates on its own to test dedupe in isolation.
        e1, _ = f.should_escalate(
            "workflow_run", _wr("completed", "failure"), delivery_id="del-1"
        )
        e2, reason = f.should_escalate(
            "workflow_run", _wr("completed", "failure"), delivery_id="del-1"
        )
        assert e1 is True
        assert e2 is False
        assert reason == "duplicate_delivery"

    def test_different_delivery_ids_both_escalate(self) -> None:
        f = WebhookFilter()
        e1, _ = f.should_escalate(
            "workflow_run", _wr("completed", "failure"), delivery_id="del-1"
        )
        e2, _ = f.should_escalate(
            "workflow_run", _wr("completed", "failure"), delivery_id="del-2"
        )
        assert e1 is True
        assert e2 is True

    def test_dedupe_disabled_when_no_delivery_id(self) -> None:
        """No delivery_id -> dedupe layer is bypassed entirely."""
        f = WebhookFilter()
        e1, _ = f.should_escalate("workflow_run", _wr("completed", "failure"))
        e2, _ = f.should_escalate("workflow_run", _wr("completed", "failure"))
        assert e1 is True
        assert e2 is True


class TestWebhookFilterOverrides:
    def test_drop_success_false_lets_clean_runs_through(self) -> None:
        f = WebhookFilter(drop_success=False)
        escalate, _ = f.should_escalate("workflow_run", _wr("completed", "success"))
        assert escalate is True

    def test_explicit_drop_events_overrides_defaults(self) -> None:
        # Operator passes empty-set explicitly: nothing in the
        # static-drop-list category gets dropped.
        f = WebhookFilter(drop_events=set())
        escalate, _ = f.should_escalate("ping", {})
        assert escalate is True

    def test_custom_drop_events(self) -> None:
        f = WebhookFilter(drop_events={"issues"})
        escalate, reason = f.should_escalate("issues", {"action": "labeled"})
        assert escalate is False
        assert reason == "issues"

    def test_custom_action_keyed_drop(self) -> None:
        f = WebhookFilter(drop_events={"pull_request.synchronize"})
        # pull_request.synchronize is dropped, but pull_request.opened gets
        # through.
        e1, _ = f.should_escalate(
            "pull_request", {"action": "synchronize", "number": 1}
        )
        e2, _ = f.should_escalate("pull_request", {"action": "opened", "number": 2})
        assert e1 is False
        assert e2 is True


class TestWebhookStats:
    def test_counters_increment(self) -> None:
        f = WebhookFilter()
        f.should_escalate("ping", {})  # drop
        f.should_escalate("workflow_run", _wr("completed", "failure"))  # esc.
        f.should_escalate("workflow_run", _wr("queued"))  # drop

        snap = f.stats.snapshot()
        assert snap["events_seen_total"] == 3
        assert snap["events_dropped_total"] == 2
        assert snap["events_escalated_total"] == 1
        assert snap["last_event_type"] == "workflow_run"
        assert snap["last_event_at"] is not None
        # ISO8601 with Z suffix per spec
        assert snap["last_event_at"].endswith("Z")

    def test_drop_reasons_breakdown(self) -> None:
        f = WebhookFilter()
        f.should_escalate("ping", {})
        f.should_escalate("ping", {})
        f.should_escalate("workflow_run", _wr("queued"))

        snap = f.stats.snapshot()
        assert snap["drop_reasons"]["ping"] == 2
        assert snap["drop_reasons"]["workflow_run.queued"] == 1

    def test_empty_snapshot_shape(self) -> None:
        s = WebhookStats()
        snap = s.snapshot()
        assert snap == {
            "status": "ok",
            "last_event_at": None,
            "last_event_type": None,
            "events_seen_total": 0,
            "events_dropped_total": 0,
            "events_escalated_total": 0,
            "drop_reasons": {},
        }
