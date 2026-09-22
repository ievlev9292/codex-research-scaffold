# Close a run on user request

The user's ordinary instruction to close the run is sufficient. Reconcile its existing record with retained artifacts: completed outcomes, unresolved questions, the status of checks, reports and independent reviews, limitations and the next useful action. Move genuinely future questions into BACKLOG.md with evidence links; do not duplicate active histories.

Save recovery-critical state first. Update relevant source/artifact/report metadata and verify required local links. Resume partial closure from saved records after interruption; avoid repeating completed work or changing immutable execution evidence.

Use tools/runs.py close RUN_ID --user-requested only for an actual user closure request. The flag records caller intent; it is not an authorization mechanism. The helper updates state, the run index and the handoff without manufacturing scientific completion. Inspect its audit_due result: every five distinct closed runs, suggest a small documentation audit in the closure response. Record that suggestion with audit-offered when including it in the response. Repeated closure must not recount the run.

The suggestion is optional and does not block other work. If accepted, load [documentation audit](audit_project.md). Closure neither launches that audit nor automatically commits, deletes, restructures or publishes project files.
