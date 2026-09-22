# Small project documentation audit

Run when the user accepts the suggestion or explicitly requests an audit. Use tools/check_project.py audit for inexpensive directory statistics and mechanical findings, then inspect current controls and a bounded sample of recent runs.

Look for duplicated/contradictory instructions or records, unnecessary detail, oversized handoffs/backlogs, stale links/indexes, and disproportionate documentation or extraction/search-cache growth. Preserve useful scientific reasoning, failures, historical reports and source provenance. State sampling limits; this is not a scientific recalculation or exhaustive source review.

Present at most five prioritized recommendations, with concrete locations and a proposed action. Keep a short latest finding summary in existing project records; link actionable items into BACKLOG.md where useful. No separate audit report is required by default. Auditing itself does not authorize deletion or restructuring.

Record completion through tools/runs.py audit-completed --user-requested. A completed audit restarts the default five-closed-run interval. If a suggestion is declined or deferred, wait another five closed runs unless instructed otherwise. Audit maintenance is not a research run and creates no numerical workload.
