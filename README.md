# Portable research scaffold

A starting folder for scientific research with OpenAI Codex. It keeps sources, calculations, checks and reports together, with context to continue your work in later sessions.

## Getting started

1. Copy this scaffold into a new project folder, including the hidden `.agents/` folder.
2. Put your papers and reference material in `sources/human/`, and your input datasets in `data/raw/human/`.
3. Open the project folder in Codex and ask: **"Initialize this research project using the supplied sources."**
4. Describe your research question, the result you want, and any limits on scope or computing resources.

Initialization checks the available tools and supplied sources, identifies gaps, and prepares the project for work. You can adapt the [example prompts](sources/prompts/) if you want a more detailed starting request.

## Working on a project

Ask for research, calculations or a report in ordinary language. The agent records findings, runs relevant checks and keeps track of unresolved questions. Reports receive independent review and corrections before rendering and page inspection.

Say **"Close the run"** when you want the current run closed. Its results and open questions are saved for future work. Every five closed runs, the agent suggests a small documentation audit.

## Where to find things

| Location | Contents |
|---|---|
| `sources/` | Papers, reference material and example prompts |
| `data/` | Input datasets and shared derived data |
| `calculations/` | Scripts, checks and their outputs |
| `reports_tex/` | LaTeX reports, PDFs and included figures |
| `research/` | Run records and research notes |
| `PROJECT_HANDOFF.md` | Current project status and next action |
| `BACKLOG.md` | Questions and ideas for future work |

The remaining folders support the agent's instructions, tool settings and local search.

## Requirements

- OpenAI Codex.
- Python 3.10 or later with SQLite FTS5 support. PDF text extraction also needs `pypdf`.
- Scientific packages and tools appropriate to your work, such as Python libraries or Mathematica.
- For the default report workflow: LaTeX, the ARS research skill and an independent reviewing agent. TikZ diagrams use the `tikz-diagrams` skill.

These dependencies are not bundled. Initialization checks what is available and recommends any setup or updates; installation and updates require your permission.

When moving a project to another computer, keep the entire folder and ask Codex to initialize it again to check that computer's tools and resources.
