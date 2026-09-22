# Add or revise a package

1. Identify authoritative documentation/source, intended version, dependencies, entry points and compatible kernel/environment. Inspect plain-text material first. Notebook-only documentation remains outside scope unless the user requests its inspection.
2. Give host-appropriate installation instructions and intended locations. Naming a package is not authorization to install it. Follow existing explicit installation authorization without asking again; never install during a read-only audit.
3. Inspect the available installation and run a small documented .wl example with a known expected result. Record actual version/kernel/host/environment, observed outputs and limits. An absent or failing package remains pending/failed.
4. Add an evidence-backed entry with tools/registry.py add, then run review. Consult config/wolfram_packages.schema.json for fields. Host-specific paths belong in local bindings. Record installation, validation and permitted capabilities separately. At actual validation, capture registry.py binding-identity KEY and save its identity as validation.binding_identity; a changed binding needs a new check, not merely a refreshed receipt.
5. Review duplicates/shadowing, dependency references, versions/variants, environment membership and stale evidence. Recheck affected combinations; do not test every unrelated package pair.

A new package normally changes registry data, not the core skill. Compatible use is scoped to the environment actually tested. As one relevant example, a FeynCalc-patched FeynArts environment and an unpatched FeynArts/FormCalc environment should be treated separately and verified according to their authoritative documentation.
