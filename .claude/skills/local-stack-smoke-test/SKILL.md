---
name: local-stack-smoke-test
description: Safely exercise a cv-ranker change against the real local Ollama/Qdrant/Postgres stack, and clean up any test data afterward. Use before declaring a change to ingest/process/find/the LLM or embedding path done.
---

# Smoke-testing against the real local stack

Unit tests in this repo (`tests/test_ranker.py`, `tests/test_db.py`) don't
exercise the CLI layer or a live LLM/embedding server. Several real bugs
here were only caught by actually running the command against the live
local stack — passing `py_compile`/unit tests is not sufficient evidence
that an `ingest`/`process`/`find` change works.

## Before you start

Check what's already running rather than assuming:

```bash
curl -s -o /dev/null -w "ollama:%{http_code}\n" http://localhost:11434 --max-time 2
curl -s -o /dev/null -w "qdrant:%{http_code}\n" http://localhost:6333 --max-time 2
```

If Qdrant/Postgres aren't up, use `/stack-up` (or `docker compose up -d`
from `docker/`). Ollama runs outside Docker Compose here — if it's not
responding, ask the developer to start it rather than trying to launch it
yourself.

## Running a real command

Use the venv's interpreter with `PYTHONPATH=src`, e.g.:

```bash
PYTHONPATH=src .venv/bin/python3 -m cv_ranker find --criteria "..." --top-k 5 --output json
```

For `ingest`, create a throwaway CV file under the scratchpad directory
(never inside `tests/fixtures/`, which is committed test data) so cleanup is
unambiguous.

## Cleaning up afterward

Any row/point you create while smoke-testing against the **real** local
Postgres/Qdrant (not a throwaway testcontainer) must be removed once you've
confirmed the behavior — this is shared, persistent local data, not a
sandbox:

1. Note the `cv_id` printed by `ingest`.
2. Delete the Qdrant points by payload filter (works whether the CV
   produced one legacy whole-CV point or several `chunk_type` points):

   ```bash
   API_KEY=$(grep CV_RANKER_QDRANT_API_KEY config/local.env | cut -d= -f2)
   curl -s -H "api-key: $API_KEY" -X POST \
     "http://localhost:6333/collections/cv_embeddings/points/delete" \
     -H "Content-Type: application/json" \
     -d '{"filter": {"must": [{"key": "cv_id", "match": {"value": <cv_id>}}]}}'
   ```

3. Delete the Postgres row:

   ```bash
   DSN=$(grep CV_RANKER_DB_DSN config/local.env | cut -d= -f2)
   PYTHONPATH=src .venv/bin/python3 -c "
   import psycopg
   with psycopg.connect('$DSN') as conn:
       conn.execute('DELETE FROM cvs WHERE id = <cv_id>')
       conn.commit()
   "
   ```

4. Remove the scratchpad CV file you created.

Never print or otherwise expose the actual value of
`CV_RANKER_QDRANT_API_KEY` — read it into a shell variable and use it, don't
echo it into chat output.
