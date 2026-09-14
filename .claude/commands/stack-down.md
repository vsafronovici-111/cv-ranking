---
description: Stop the local Postgres + Qdrant Docker stack
---

Run `docker compose down` from the `docker/` subfolder of this repo (NOT
`docker compose down -v` — this project's Postgres/Qdrant data lives in bind
mounts under `docker/volume/`, not named volumes, but `-v` also removes
anonymous volumes and is unnecessary here; the bind-mounted data on disk
persists across `down`/`up` either way, so there's no need to risk it).
Confirm the containers stopped and report briefly.
