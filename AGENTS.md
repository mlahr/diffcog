# AGENTS.md

## Project Notes

- This is a Python prototype using `uv`, `pytest`, and `ruff`.
- Keep the CLI contract aligned with `CLI.md`.
- Use tracked `.java` files only unless the scope is explicitly changed.
- Keep complexity scoring separate from git plumbing and reporting.
- Run `uv run diffcog-check` before handing off changes.

## About testing

- prefer quick unit tests
- never test logging behaviour
- never test if a particular configuration option is in place


