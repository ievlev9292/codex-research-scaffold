# Prepare a research report

Reconcile the existing run task list with the intended report. Include supported outcomes and material limitations; record deliberate omissions. Check that equations, values, conventions and claim strength match their supporting notes and calculations.

Create a timestamped, self-contained bundle under reports_tex/. Use the required TeX engine and selected bibliography route. On hosts requiring direct executable invocation, invoke each exact configured program directly with workdir set to the source or auxiliary-file directory. Do not silently substitute engines or install missing packages; MiKTeX probes/builds use --disable-installer when installations are not authorized.

Computational figures stay with the generating execution. Copy the exact included rendered version into the report's figures/ for preservation. Its INDEX.md identifies the included filename/label, source artifact, generating script/source version, execution/data reference and modifications. Link detailed uncertainty and processing choices rather than copying them. Report-only diagram sources may live here directly; inline diagrams can cite their TeX location.

Compile and inspect the actual PDF non-interactively, including representative pages, references and figures. Record unresolved compilation or scientific limitations. Keep useful build metadata. Register the version and locators through report_locator.py, then verify representative section/equation lookups against the actual artifact. Unknown parser coverage is not successful mapping.

Use tools/check_project.py for mechanical links and figure coverage; it cannot establish scientific correctness. A working build is not a completed scientific review.

Before delivering a final research report, obtain an independent review from at least one separate agent that did not author it, unless the user explicitly waives review. This standing request authorizes bounded reviewer delegation without an additional permission checkpoint. Give the reviewer the final TeX/PDF, research request/scope and linked source/calculation evidence. Review consequential claims, assumptions, equations, numerical checks, citations, task coverage and presentation; identify any uninspected scope.

Address material findings through corrections or explicit scientific limitations. Recompile and inspect affected artifacts, and have substantive revisions rechecked. Tie review completion to the delivered version. Record that version, concise findings/disposition and unresolved limitations in RUN.md, linking existing evidence rather than requiring a separate review dossier. If an independent reviewer is unavailable, retain draft/pending-review status, flag it at the next natural update and continue unaffected work. Self-review does not satisfy independent review; record an explicit waiver as waived, not passed.

Prose polishing through de-ai-polish-writing remains explicit-only.

Report preparation does not close the run or authorize opening/attaching any UI panel.
