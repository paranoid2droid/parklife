# AGENTS.md

Entry point for any AI coding agent (Codex, Claude Code, etc.) working in this repo.

## Read first, in this order

1. **[CLAUDE.md](CLAUDE.md)** — project knowledge: what this is, commands, architecture, conventions. Stable, read once per session. The name is historical; the contents are agent-agnostic.
2. **[HANDOFF.md](HANDOFF.md)** — live cross-agent state: current focus, in-progress work, blockers, next-up TODOs, recent-session log. Read at session start, update at session end.
3. **[SUMMARY.md](SUMMARY.md)** — deep history and rationale. Reference when context is missing, not on every session.
4. **[RUN_LOG.md](RUN_LOG.md)** — long-running batch operational log. Reference only when working on those batches.

## Working agreement

- **Source of truth for what to do next is HANDOFF.md.** Don't take work direction from agent-private memory or from chat scrollback alone — if it's not in HANDOFF.md, it's not yet committed shared state.
- **Update HANDOFF.md before quota/session ends.** Concrete pointers (file paths, line numbers, exact next command) — assume the next agent has zero memory of your session.
- **Don't delete another agent's notes** without confirming the work is done. Move uncertain items to "Blocked / waiting" with a question.
- Tag entries with your agent name: `(Claude)` or `(Codex)`.

## Conventions specific to this repo

See CLAUDE.md "Conventions" and "Operational notes" sections. Highlights:
- Python venv at `.venv/`, run modules via `.venv/bin/python -m scripts.X`.
- 1 req/sec on external sites; descriptive User-Agent; respect robots.txt.
- Never lose `observation.raw_name`; aliases are first-class via `species_alias`.
- Re-run `scripts.dedupe` after any `observation` change before exporting.
