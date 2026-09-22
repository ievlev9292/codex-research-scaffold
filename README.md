# Portable research scaffold v2

Requires Python 3.10+ with SQLite FTS5; PDF text extraction additionally needs pypdf. Scientific backends and report tools are checked at initialization, not bundled. Windows, macOS and Linux use the same Python helpers; select the actual executables on each host. Keep the copy path reasonably short on Windows systems with legacy path limits.

Copy this entire folder, including .agents/, into a new project. Put supplied material in sources/human/ and data/raw/human/. Tell the agent to initialize the project, using sources/prompts/example_initialize_project.md if useful. No third-party scientific package is preinstalled or registered by this scaffold.

AGENTS.md routes instructions. PROJECT_HANDOFF.md points to current work; research/runs/ holds its history. Initialization creates local host bindings and audits capabilities without installing or updating anything.

## Layout

| Location | Purpose |
|---|---|
| .agents/skills/ | Python, Wolfram and explicit-only prose editing |
| workflows/ | Instructions loaded for the current operation |
| config/ | Portable defaults, empty registry, generated host bindings |
| catalog/ | Durable manifests, derived text and search index |
| tools/ | Small CLI helpers; each supports --help |
| sources/ | Originals, acquired literature and prompt examples |
| data/ | Original and shared derived datasets |
| research/ | Run records and reusable reasoning |
| calculations/ | Task-specific scripts, checks and retained executions |
| reports_tex/ | Self-contained report versions and figure provenance |
| log/ | Exceptional project-level operational records |
| tmp/ | Unique scratch directories |

Read [initialization](workflows/initialize.md) for the first commands. Helpers accept an explicit project root and also resolve their own copied location. Use the selected Python executable directly; command examples use PYTHON as a placeholder for its actual executable path.

After moving an initialized project, run initialization again to rebind local tools and reassess host limits. Relative evidence links and report identities travel with the project; old capability and package-validation receipts do not automatically authorize the new environment.

The bare copy contains no live host profile, database, research results or configured Wolfram packages. Optional calculation/input/tests/shared folders are created when useful. Search caches are rebuildable; manifests and scientific records preserve evidence.

Say “close the run” when ready. Every five closed research runs, the agent suggests a small documentation audit. Running or declining that audit leaves other authorized work unaffected.
