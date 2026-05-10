# JAR-136 — Delivery metrics dashboard

Purpose: daily operator view for Claude Telegram bridge delivery outcomes.

Source events: structured `delivery` logs emitted by `src/claude/sdk_integration.py`.

Fields used:
- `delivery_kind`: one of `text`, `tool_summary_internal`, `final_user_response`, `error_fallback`.
- `timestamp` or `date`: ISO-like timestamp; first 10 chars define the day.

Dashboard rule:
- Count only structured delivery events. Ignore unrelated logs such as `claude_run_complete`.
- Daily rate = `tool_summary_internal / total_delivery_events`.
- Alert if rate > 5%.

Programmatic use:
```python
from src.claude.sdk_integration import (
    delivery_metrics_report,
    format_delivery_metrics_dashboard,
)

report = delivery_metrics_report(events)
print(format_delivery_metrics_dashboard(report))
```

Example output:
```text
Delivery metrics dashboard
date | total | tool_summary_internal | rate | status
2026-05-10 | 20 | 2 | 10.00% | ALERT
```
