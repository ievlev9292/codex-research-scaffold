# Calculation records

Organize by scientific purpose: calculations/<topic>/ may contain Python and Wolfram scripts together. Add input/, checks/, tests/, scripts/ or shared/ only when complexity or actual reuse warrants them. Original shared data stays in data/raw/; shared derived datasets have one authoritative location in data/derived/.

Retain meaningful executions or batches under output/<timestamp>/. A compact execution.json (or equivalent record) identifies the run, exact command/workdir, code version or recoverable snapshot, input identities/resolved settings, environment, relevant precision/seed/thread settings, actual outputs, check evidence and limitations. A hash alone cannot restore overwritten code.

Keep check measurements and useful diagnostics beside results. Link scientific interpretation instead of copying it into several records. Preserve significant failed attempts. Group sweeps rather than creating a prose report per point. Expensive restart state is saved when useful.

Record consequential uncertainty contributions, exclusions, normalization, binning, cuts, interpolation or smoothing in the generating configuration/script and execution evidence. Explain scientific choices briefly; keep underlying data recoverable. Plot saved data independently of expensive solvers. Included report figures are version-preserving rendered snapshots with provenance links.

Use an existing derivation/result note for later assessments; do not rewrite immutable old execution evidence. Follow workflows/research.md for scientific verification and the selected backend skill for execution.
