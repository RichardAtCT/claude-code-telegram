from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from src.lockstep.db import (
    cancel_checkin,
    create_goal,
    ensure_tables,
    get_db,
    get_history,
    get_summary,
    list_checkins,
    list_goals,
    record_outcome,
    schedule_checkin,
    update_goal,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="lockstep",
        description="Goal Tracking CLI for the Lockstep system",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # set-goal
    p_set = sub.add_parser("set-goal", help="Create a new goal")
    p_set.add_argument("--title", required=True, help="Goal title")
    p_set.add_argument("--why", required=True, help="Why this goal matters")
    p_set.add_argument(
        "--timeframe",
        required=True,
        choices=["yearly", "monthly", "weekly"],
        help="Goal timeframe",
    )
    p_set.add_argument(
        "--period", required=True, help="Period string (e.g. 2026, 2026-03, 2026-W11)"
    )
    p_set.add_argument("--parent-goal-id", default=None, help="Parent goal ID")
    p_set.add_argument("--description", default=None, help="Goal description")

    # update-goal
    p_upd = sub.add_parser("update-goal", help="Update an existing goal")
    p_upd.add_argument("--goal-id", required=True, help="Goal ID to update")
    p_upd.add_argument(
        "--status",
        choices=["active", "completed", "dropped"],
        default=None,
        help="New status",
    )
    p_upd.add_argument("--title", default=None, help="New title")

    # record
    p_rec = sub.add_parser("record", help="Record a daily outcome")
    p_rec.add_argument("--goal-id", required=True, help="Goal ID")
    p_rec.add_argument(
        "--status",
        required=True,
        choices=["completed", "partial", "skipped", "missed"],
        help="Outcome status",
    )
    p_rec.add_argument("--reason", default=None, help="Reason (for skipped/missed)")
    p_rec.add_argument("--date", default=None, help="Date in YYYY-MM-DD format")
    p_rec.add_argument("--notes", default=None, help="Additional notes")

    # list
    p_list = sub.add_parser("list", help="List goals")
    p_list.add_argument(
        "--timeframe",
        choices=["yearly", "monthly", "weekly"],
        default=None,
        help="Filter by timeframe",
    )
    p_list.add_argument("--period", default=None, help="Filter by period")
    p_list.add_argument("--status", default="active", help="Filter by status or 'all'")

    # history
    p_hist = sub.add_parser("history", help="Get outcome history")
    p_hist.add_argument("--goal-id", default=None, help="Filter by goal ID")
    p_hist.add_argument(
        "--days", type=int, default=7, help="Number of days to look back"
    )
    p_hist.add_argument(
        "--status",
        choices=["completed", "partial", "skipped", "missed"],
        default=None,
        help="Filter by outcome status",
    )

    # summary
    p_sum = sub.add_parser("summary", help="Get period summary")
    p_sum.add_argument(
        "--period",
        required=True,
        help="Period to summarize (e.g. 2026-03 or 2026-W11)",
    )

    # schedule-checkin
    p_sched = sub.add_parser("schedule-checkin", help="Schedule a checkin")
    p_sched.add_argument("--time", required=True, help="Time in HH:MM format (UTC)")
    p_sched.add_argument("--context", required=True, help="Checkin context/message")
    p_sched.add_argument("--user-id", type=int, default=0, help="Telegram user ID")
    p_sched.add_argument("--chat-id", type=int, default=0, help="Telegram chat ID")
    p_sched.add_argument("--session-id", default=None, help="Session ID")

    # list-checkins
    p_lc = sub.add_parser("list-checkins", help="List scheduled checkins")
    p_lc.add_argument("--status", default="pending", help="Filter by status")

    # cancel-checkin
    p_cc = sub.add_parser("cancel-checkin", help="Cancel a scheduled checkin")
    p_cc.add_argument("--id", required=True, help="Checkin ID to cancel")

    return parser


def _compute_fire_at(time_str: str) -> str:
    """Parse HH:MM and return ISO timestamp. If past today, schedule tomorrow."""
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])

    now = datetime.now(timezone.utc)
    fire_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fire_at <= now:
        fire_at += timedelta(days=1)
    return fire_at.isoformat()


def main() -> None:
    """Entry point for the Goal Tracking CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    try:
        conn = get_db()
        ensure_tables(conn)

        result: dict | list[dict]

        if args.command == "set-goal":
            result = create_goal(
                conn,
                title=args.title,
                why=args.why,
                timeframe=args.timeframe,
                period=args.period,
                parent_goal_id=args.parent_goal_id,
                description=args.description,
            )
        elif args.command == "update-goal":
            result = update_goal(
                conn,
                goal_id=args.goal_id,
                status=args.status,
                title=args.title,
            )
        elif args.command == "record":
            result = record_outcome(
                conn,
                goal_id=args.goal_id,
                status=args.status,
                reason=args.reason,
                date=args.date,
                notes=args.notes,
            )
        elif args.command == "list":
            result = list_goals(
                conn,
                timeframe=args.timeframe,
                period=args.period,
                status=args.status,
            )
        elif args.command == "history":
            result = get_history(
                conn,
                goal_id=args.goal_id,
                days=args.days,
                status=args.status,
            )
        elif args.command == "summary":
            result = get_summary(conn, period=args.period)
        elif args.command == "schedule-checkin":
            fire_at_str = _compute_fire_at(args.time)
            result = schedule_checkin(
                conn,
                fire_at_str=fire_at_str,
                context=args.context,
                user_id=args.user_id,
                chat_id=args.chat_id,
                session_id=args.session_id,
            )
        elif args.command == "list-checkins":
            result = list_checkins(conn, status=args.status)
        elif args.command == "cancel-checkin":
            result = cancel_checkin(conn, checkin_id=args.id)
        else:
            raise ValueError(f"Unknown command: {args.command}")

        print(json.dumps(result, indent=2, default=str))
        conn.close()

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
