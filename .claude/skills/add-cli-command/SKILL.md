---
name: add-cli-command
description: Add a new cv-ranker CLI subcommand, following this repo's established argparse + config + README conventions. Use whenever asked to add a new `cv-ranker` subcommand or CLI flag group.
---

# Adding a `cv-ranker` CLI subcommand

This repo's `src/cv_ranker/cli.py` has one consistent shape for every
subcommand (`ingest`, `process`, `report`, `status`, `find`). Follow it
exactly rather than inventing a new structure — consistency here matters
more than any single command's internal cleverness.

## Steps

1. **Add the subparser** in `build_parser()`. Add flags with `add_argument`,
   giving every flag a `help=` string. If the subparser has no extra
   arguments (like `status`), don't assign it to a variable — `ruff`'s
   `F841` flags an unused `status_parser`-style binding.

2. **Decide whether the command needs the Postgres queue (`CVStore`).** Most
   commands do (`ingest`, `process`, `report`, `status`) and go through the
   default path in `main()` that creates `CVStore` and calls
   `store.init_schema()` before dispatch. If the command only needs Qdrant
   and/or the LLM/embedding servers (like `find`), dispatch it *before* that
   Postgres setup in `main()` — don't force a Postgres dependency on a
   command that doesn't need one.

3. **Write a dedicated `_run_<command>(args)` (or `_run_<command>(store,
   args)`) function.** Load settings via the `load_*_settings(args.env)`
   functions from `config.py` — never read `os.environ` directly in
   `cli.py`. Construct the client/store objects the same way the existing
   commands do (see `_run_ingest` for the fullest example: `LLMClient`,
   `EmbeddingClient`, `CVVectorStore` all built from a `*Config`/`*Settings`
   pair).

4. **Handle both `--output text` and `--output json`** if the command
   produces results a human or a script might consume — match the existing
   `report`/`find` pattern (JSON via `json.dumps(payload, indent=2)`, text
   via a numbered list with the file/id, key fields, and a `score` if
   relevant).

5. **Catch the specific `*Error` classes**, not bare `Exception`, when
   calling into a client/store (e.g. `EmbeddingClientError`,
   `CVVectorStoreError`, `LLMClientError`) — print a short message and
   return a non-zero exit code rather than letting a traceback surface.

6. **Update the README** in the same change:
   - Add the command to the "split into stages" list (or its own bullet if
     it doesn't fit the ingest→process→report pipeline).
   - Add a runnable example under the "Local (Ollama, default)" section.
   - If the command has non-obvious behavior (e.g. it doesn't touch
     Postgres), call that out explicitly, the way `find`'s section does.

7. **Test against the real local stack before calling it done** — see the
   `local-stack-smoke-test` skill. Unit tests in this repo don't cover the
   CLI layer; running the actual command against Ollama/Qdrant/Postgres is
   the only way to catch integration bugs (this is how a real crash in
   `ranker.py`'s LLM-fallback path and a missing `_run_find` DB dependency
   were caught in past sessions).

## Example: the `find` command

`find` (`cli.py`) is the clearest reference implementation of a
Qdrant-only, no-Postgres-needed command:

- Its subparser is added in `build_parser()` alongside the others.
- `main()` special-cases `args.command == "find"` to return
  `_run_find(args)` *before* the `CVStore`/`init_schema()` setup, since it
  needs neither.
- `_run_find` builds an `EmbeddingClient` + `CVVectorStore` from
  `load_embedding_settings`/`load_qdrant_settings`, embeds the free-text
  criteria, calls `vector_store.search_similar(...)`, and prints results in
  both `text` and `json` shapes.
