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

spacedock runs this declaratively from `.dotfiles`
(`containers/services/avec-moi-app.nix`, flake input `avec-moi`, port 8081).
`nixos/avec-moi-app.nix` here is the updated version of that module: it adds
the `/var/lib/avec-moi:/data` volume for questions and reads `ADMIN_PASSWORD`
from the sops secret `avec-moi-env`.

1. `just sops` in .dotfiles → add `avec-moi-env: ADMIN_PASSWORD=...`
2. Copy `nixos/avec-moi-app.nix` over `.dotfiles/containers/services/avec-moi-app.nix`
3. Rebuild spacedock:
   - to preview this branch before merging:
     `sudo nixos-rebuild switch --flake .#spacedock --override-input avec-moi github:gignsky/avecmoi/claude/kind-euler-pqpy4v`
   - after merging: `nix flake update avec-moi`, then rebuild as usual

Questions land in `/var/lib/avec-moi/questions.jsonl` (one JSON object per
line: `id, submitted_at, anonymous, name, topic, question`) and survive
rebuilds.

Without NixOS: `nix build && podman load -i result && podman run -d -p 8081:8080 -v avecmoi-data:/data -e ADMIN_PASSWORD=... avecmoi:latest`

## Local preview

```sh
nix run .#serve                 # http://127.0.0.1:8080, questions -> ./data/
ADMIN_PASSWORD=test nix run .#serve
```

## Privacy

Email addresses are never collected. Anonymous submissions store no name. No IP addresses are written to
disk or to the access log; the per-client rate limit (8 per 10 min) is kept in
memory only.
