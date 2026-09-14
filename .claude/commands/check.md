---
description: Run ruff lint/format check and the unit test suite
---

Run this project's full local check loop and report the results concisely
(pass/fail per step; on failure, show the relevant error output, don't just
say "it failed"):

1. `.venv/bin/ruff check .`
2. `.venv/bin/ruff format --check .`
3. `PYTHONPATH=src .venv/bin/python3 -m unittest tests.test_ranker -v`
4. If Docker is running, also run `PYTHONPATH=src .venv/bin/python3 -m unittest tests.test_db -v`
   (needs `testcontainers` — install via `.venv/bin/pip install -e ".[test]"`
   if missing). If Docker isn't running, skip this step and say so rather
   than treating it as a failure.

Do not modify any files as part of this command — if ruff reports fixable
issues, mention them but let the developer decide whether to run
`ruff check --fix` (the PostToolUse hook already auto-fixes most issues as
files are edited, so a clean check here usually means nothing to do).
