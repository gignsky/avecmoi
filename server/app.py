#!/usr/bin/env python3
"""avecmoi.app — Ask an Appraiser question box.

Serves the static site and accepts question submissions, appending each one
as a JSON line to $DATA_DIR/questions.jsonl so they survive container
restarts (mount a host directory at $DATA_DIR on spacedock).

Standard library only, so the Nix/OCI build needs nothing but python3.

Environment:
  SITE_DIR        directory served at /            (default: ../site)
  ARCHIVE_DIR     directory served at /matter/     (default: ../archive/why-appraisers-matter)
  DATA_DIR        where questions.jsonl lives      (default: ./data)
  ADMIN_PASSWORD  enables /admin (HTTP Basic, any username). Unset = /admin disabled.
  HOST, PORT      bind address                     (default: 0.0.0.0:8080)
"""

import base64
import csv
import hmac
import html
import io
import json
import mimetypes
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
SITE_DIR = Path(os.environ.get("SITE_DIR", HERE.parent / "site")).resolve()
ARCHIVE_DIR = Path(
    os.environ.get("ARCHIVE_DIR", HERE.parent / "archive" / "why-appraisers-matter")
).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", HERE / "data")).resolve()
QUESTIONS_FILE = DATA_DIR / "questions.jsonl"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

MAX_BODY = 16 * 1024
MAX_QUESTION = 4000
MAX_NAME = 120
MAX_TOPIC = 60
TOPICS = {
    "uad36",
    "urar",
    "ratings",
    "measurement",
    "comps",
    "rebuttals",
    "working-with-appraisers",
    "other",
}

# Rate limit: at most RATE_MAX submissions per RATE_WINDOW seconds per client.
# Kept in memory only; client addresses are never written to disk.
RATE_MAX = 8
RATE_WINDOW = 600
_rate = {}
_rate_lock = threading.Lock()
_write_lock = threading.Lock()


def _rate_ok(client):
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate.get(client, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_MAX:
            _rate[client] = hits
            return False
        hits.append(now)
        _rate[client] = hits
        if len(_rate) > 10000:  # keep memory bounded
            _rate.clear()
        return True


def _clean(value, limit):
    """Single-line field: collapse whitespace and truncate."""
    return " ".join(str(value or "").split())[:limit]


def _clean_text(value, limit):
    """Multi-line field: normalise newlines, trim, truncate."""
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def save_question(fields):
    """Validate and persist one submission. Returns (ok, message)."""
    if fields.get("website"):  # honeypot; real people never see this field
        return True, "Thanks!"
    question = _clean_text(fields.get("question"), MAX_QUESTION)
    if len(question) < 5:
        return False, "Please type a question (at least a few words)."
    anonymous = str(fields.get("anonymous", "")).lower() in ("1", "true", "on", "yes")
    name = "" if anonymous else _clean(fields.get("name"), MAX_NAME)
    topic = _clean(fields.get("topic"), MAX_TOPIC)
    if topic not in TOPICS:
        topic = "other"
    record = {
        "id": uuid.uuid4().hex[:12],
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "anonymous": anonymous or not name,
        "name": name,
        "topic": topic,
        "question": question,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _write_lock, open(QUESTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    return True, "Thanks! Your question has been saved for the session."


def load_questions():
    if not QUESTIONS_FILE.exists():
        return []
    out = []
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


TOPIC_LABELS = {
    "uad36": "UAD 3.6 in general",
    "urar": "The new URAR report",
    "ratings": "Quality & condition ratings",
    "measurement": "Measurement / GLA (ANSI)",
    "comps": "Comparables & adjustments",
    "rebuttals": "Reconsideration of value",
    "working-with-appraisers": "Working with appraisers",
    "other": "Something else",
}


def render_admin(questions):
    rows = []
    for q in reversed(questions):
        who = "Anonymous" if q.get("anonymous") else html.escape(q.get("name", ""))
        rows.append(
            "<tr><td class=when>{when}</td><td>{who}</td><td>{topic}</td><td class=q>{text}</td></tr>".format(
                when=html.escape(q.get("submitted_at", "").replace("T", " ").replace("+00:00", " UTC")),
                who=who,
                topic=html.escape(TOPIC_LABELS.get(q.get("topic"), q.get("topic", ""))),
                text=html.escape(q.get("question", "")).replace("\n", "<br>"),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan=4 class=empty>No questions yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Submitted Questions</title>
<style>
body{{margin:0;font:15px/1.5 system-ui,-apple-system,sans-serif;background:#F5F3EE;color:#2E3234}}
header{{background:#2E3234;color:#F5F3EE;padding:20px 16px}}
header h1{{margin:0;font:700 22px Georgia,serif}} header span{{color:#FFB81C}}
main{{padding:16px;max-width:1100px;margin:0 auto}}
.bar{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}}
a.btn{{background:#FFB81C;color:#2E3234;padding:8px 14px;border-radius:6px;text-decoration:none;font-weight:600}}
.wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}}
th,td{{text-align:left;padding:10px;border-bottom:1px solid #e4e1d9;vertical-align:top}}
th{{background:#e9e6de;font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
td.when{{white-space:nowrap;font-size:13px;color:#666}} td.q{{min-width:280px}}
td.empty{{text-align:center;color:#888;padding:32px}}
</style></head><body>
<header><h1>Ask an Appraiser <span>·</span> Submitted Questions</h1></header>
<main><div class=bar><strong>{len(questions)} question(s)</strong>
<a class=btn href="/admin/questions.csv">Download CSV</a>
<a class=btn href="/admin/questions.jsonl">Download JSONL</a></div>
<div class=wrap><table><thead><tr><th>Submitted</th><th>From</th><th>Topic</th><th>Question</th></tr></thead>
<tbody>{body}</tbody></table></div></main></body></html>"""


def questions_csv(questions):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "submitted_at", "anonymous", "name", "topic", "question"])
    for q in questions:
        w.writerow([q.get(k, "") for k in ("id", "submitted_at", "anonymous", "name", "topic", "question")])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "avecmoi"
    sys_version = ""

    # ---- helpers -------------------------------------------------------
    def _client(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or self.client_address[0]

    def _send(self, status, body, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj), "application/json")

    def _admin_ok(self):
        if not ADMIN_PASSWORD:
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain")
            return False
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
                if hmac.compare_digest(pw.encode(), ADMIN_PASSWORD.encode()):
                    return True
            except Exception:
                pass
        self._send(
            HTTPStatus.UNAUTHORIZED,
            "Authentication required",
            "text/plain",
            {"WWW-Authenticate": 'Basic realm="Ask an Appraiser admin"'},
        )
        return False

    def _static(self, root, rel):
        rel = unquote(rel).lstrip("/")
        if rel == "" or rel.endswith("/"):
            rel += "index.html"
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            return self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain")
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})

    # ---- routes --------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self._send(HTTPStatus.OK, "ok", "text/plain")
        if path in ("/admin", "/admin/"):
            if self._admin_ok():
                self._send(HTTPStatus.OK, render_admin(load_questions()), extra={"Cache-Control": "no-store"})
            return
        if path == "/admin/questions.csv":
            if self._admin_ok():
                stamp = datetime.now().strftime("%Y%m%d")
                self._send(
                    HTTPStatus.OK,
                    "﻿" + questions_csv(load_questions()),
                    "text/csv; charset=utf-8",
                    {"Content-Disposition": f'attachment; filename="questions-{stamp}.csv"', "Cache-Control": "no-store"},
                )
            return
        if path == "/admin/questions.jsonl":
            if self._admin_ok():
                data = QUESTIONS_FILE.read_bytes() if QUESTIONS_FILE.exists() else b""
                self._send(HTTPStatus.OK, data, "application/x-ndjson", {"Cache-Control": "no-store"})
            return
        # Previous site, kept intact.
        if path == "/matter":
            return self._send(HTTPStatus.MOVED_PERMANENTLY, "", extra={"Location": "/matter/"})
        if path.startswith("/matter/"):
            return self._static(ARCHIVE_DIR, path[len("/matter/"):])
        return self._static(SITE_DIR, path)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/api/questions":
            return self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain")
        wants_json = "application/json" in self.headers.get("Accept", "")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "message": "That question is too long."})
        raw = self.rfile.read(length).decode("utf-8", "replace")
        ctype = self.headers.get("Content-Type", "")
        try:
            if ctype.startswith("application/json"):
                fields = json.loads(raw or "{}")
                if not isinstance(fields, dict):
                    raise ValueError
            else:
                fields = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        except ValueError:
            return self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "Could not read your submission."})

        if not _rate_ok(self._client()):
            ok, msg, status = False, "You've sent a lot of questions quickly — please wait a few minutes and try again.", HTTPStatus.TOO_MANY_REQUESTS
        else:
            try:
                ok, msg = save_question(fields)
                status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            except OSError:
                ok, msg, status = False, "Sorry — the server couldn't save your question. Please try again.", HTTPStatus.INTERNAL_SERVER_ERROR

        if wants_json:
            return self._json(status, {"ok": ok, "message": msg})
        # No-JS fallback: bounce back to the form with a status flag.
        loc = "/?sent=1#ask" if ok else "/?error=1#ask"
        self._send(HTTPStatus.SEE_OTHER, "", extra={"Location": loc})

    def log_message(self, fmt, *args):
        # Access log without client addresses (keeps anonymous questions anonymous).
        print("%s %s" % (self.log_date_time_string(), fmt % args), flush=True)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"site={SITE_DIR} archive={ARCHIVE_DIR} data={QUESTIONS_FILE}", flush=True)
    print("admin: " + ("enabled at /admin" if ADMIN_PASSWORD else "disabled (set ADMIN_PASSWORD)"), flush=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"listening on http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
