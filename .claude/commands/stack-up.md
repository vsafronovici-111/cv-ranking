---
description: Start the local Postgres + Qdrant Docker stack
---

Run `docker compose up -d` from the `docker/` subfolder of this repo, then
run `docker compose ps` from the same folder to confirm both the `postgres`
and `qdrant` services report as healthy/running. Report the result briefly.

Remind the user that Ollama (for chat + embeddings) is separate and must be
started independently (`ollama serve`), since it isn't part of this Docker
Compose stack.
