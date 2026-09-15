# CV Ranker Web

React + Vite frontend for the `cv-ranker` REST/WebSocket API
([src/api/rest/app.py](../src/api/rest/app.py)).

## Prerequisites

- Node.js 18+ and npm
- The backend API running on `http://localhost:8000` (see below)

## Install

```bash
cd web
npm install
```

## Run

Start the backend first, from the repo root:

```bash
PYTHONPATH=src .venv/bin/python3 -m uvicorn api.rest.app:app --port 8000
```

Then start the frontend dev server:

```bash
cd web
npm run dev
```

The app runs at [http://localhost:3000](http://localhost:3000). The backend
must be reachable at `http://localhost:8000` (and its WebSocket at
`ws://localhost:8000/ws`) — the backend enables CORS for
`http://localhost:3000` specifically, so both must be running on these
default ports for the "Chat" page to load its header and connect its
WebSocket.

To point the frontend at a different backend URL, set env vars before
running (e.g. in a `.env.local` file under `web/`):

```
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

## Build

```bash
npm run build    # outputs to web/dist
npm run preview  # serves the production build on port 3000
```

## Structure

- `src/pages/ChatPage.jsx` — fetches `GET /` and shows the response as the
  page header, then renders `Chat`.
- `src/components/Chat.jsx` — owns the `/ws` WebSocket connection; wires
  `ChatHistory` (incoming messages) and `ChatBox` (outgoing messages).
