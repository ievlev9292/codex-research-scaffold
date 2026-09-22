---
name: project-wolfram
description: Run Wolfram Language scripts and scientific checks in this scaffold; manage explicitly scoped package environments through the project registry.
---

# Wolfram scripts

Use .wl scripts with the configured launcher and actual kernel. A launcher path is not evidence of a licensed working kernel; consult host audit results. No front-end or notebook operation is implicit. Any notebook-content reading, parsing, extraction, creation, conversion, editing or evaluation requires an explicit request; GUI opening has its own scope.

Read [shared research checks](../../../workflows/research.md). Use fresh kernels at meaningful job/environment boundaries, explicit assumptions/precision and auditable outputs. Do not repeat a smoke test for every tiny expression or trust successful import as scientific validation. Respect host memory, job and thread limits.

Before importing third-party packages, inspect config/wolfram_packages.json and the applicable local bindings/evidence. Distinguish registered, installed, validated and authorized capabilities. Already authorized, unchanged validated environments do not require repeated confirmation. Registry membership cannot override host permissions.

For a new package or changed environment, read [onboarding](references/package_onboarding.md). The empty shipped registry is intentional. External dependencies may be used when the task authorizes them; do not impose a blanket external-code prohibition. Keep incompatible package variants in separate kernel environments and validate relevant combinations.

Use [calculation records](../../../calculations/README.md) for code/input versions, execution evidence, checks and limitations. Retain messages and failures that matter; do not silently convert warnings into successful verification.
