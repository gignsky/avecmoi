# avecmoi.app — Ask an Appraiser

Question box for the **Ask an Appraiser: UAD 3.6** session (November 12, 2026).
Visitors submit questions with their name or anonymously; each one is appended
to `questions.jsonl` in the server's data directory for later review.

| Path | What |
| --- | --- |
| `/` | Landing page + question form (`site/index.html`) |
| `POST /api/questions` | Saves a question (JSON or plain form post) |
| `/admin` | Review questions, download CSV/JSONL — only when `ADMIN_PASSWORD` is set (HTTP Basic, any username) |
| `/matter/` | Previous site, *Why Appraisers Matter* slides (`archive/why-appraisers-matter/`); notes at `/matter/notes.html` |
| `/healthz` | Health check |

The server (`server/app.py`) uses only the Python standard library.

## Run on spacedock

```sh
nix build                       # ./result = OCI image tarball
podman load -i result
mkdir -p /srv/avecmoi
podman run -d --name avecmoi -p <hostport>:8080 \
  -v /srv/avecmoi:/data \
  -e ADMIN_PASSWORD='choose-something' \
  avecmoi:latest
```

Questions land in `/srv/avecmoi/questions.jsonl` on the host (one JSON object
per line: `id, submitted_at, anonymous, name, email, topic, question`). They
persist across container rebuilds as long as the volume is mounted.

## Local preview

```sh
nix run .#serve                 # http://127.0.0.1:8080, questions -> ./data/
ADMIN_PASSWORD=test nix run .#serve
```

## Privacy

Anonymous submissions store no name or email. No IP addresses are written to
disk or to the access log; the per-client rate limit (8 per 10 min) is kept in
memory only.
