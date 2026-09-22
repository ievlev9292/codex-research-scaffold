---
name: project-python
description: Run scientific Python calculations and numerical checks in this research scaffold using its selected environment and host resource profile.
---

# Scientific Python

Read the [shared research workflow](../../../workflows/research.md) for scientific verification and evidence ownership.

Use config/host.local.json's selected Python binding and the host's invocation rules. Verify the actual interpreter/environment; do not silently substitute one. Check current available memory before substantial work. Respect job concurrency separately from process workers and BLAS/OpenMP threads; nested parallelism can exceed the budget. Run a reduced pilot when informative.

Prefer scripts and saved data. Use precision, convergence, residuals, known limits or independent implementations suited to the scientific claim. The shared workflow owns verification criteria; record actual evidence with the calculation. Reuse an unchanged environment without repeating a complete initialization audit.

Keep seeds, resolved parameters and versions reproducible. Configure caches and temporary outputs under a unique project tmp/ or calculation execution directory. Export plots non-interactively; plot retained data without rerunning expensive calculations. Missing packages are findings, not permission to install them.

For data/figure/provenance layout, use [calculation records](../../../calculations/README.md). Add reusable tests when they exercise substantive behavior, not a mirror of implementation details.
