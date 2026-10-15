"""Local labelling page for the human check: one row at a time, keyboard driven.

Serves `human_check_review.csv` on localhost. Every label is written at once to both
`human_check_review.csv` and `human_check.csv` (columns `human_grade`, `labelled_at`), so a
closed tab or a crash loses nothing. The page never shows the judge's verdict, run or language.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any

from scrutineer.paths import Paths

GRADES = ("correct", "incorrect", "not_attempted")


class LabelStore:
    def __init__(self, paths: Paths) -> None:
        self.files = (paths.human_check_review, paths.human_check)
        self.lock = threading.Lock()

    def rows(self) -> list[dict[str, str]]:
        with self.files[0].open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def label(self, row_id: str, grade: str) -> str:
        if grade not in (*GRADES, ""):
            raise ValueError(f"invalid grade {grade!r}")
        stamp = datetime.now(UTC).isoformat(timespec="seconds") if grade else ""
        with self.lock:
            for path in self.files:
                _update_csv(path, row_id, {"human_grade": grade, "labelled_at": stamp})
        return stamp


def _update_csv(path: Path, row_id: str, values: dict[str, str]) -> None:
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    matched = [row for row in rows if row["row_id"] == row_id]
    if len(matched) != 1:
        raise KeyError(f"{row_id} not found exactly once in {path.name}")
    matched[0].update(values)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def _handler(store: LabelStore) -> type[BaseHTTPRequestHandler]:
    page = resources.files("scrutineer.grade").joinpath("labeller.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, page, "text/html; charset=utf-8")
            elif self.path == "/rows":
                self._send(200, json.dumps(store.rows(), ensure_ascii=False).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/label":
                self._send(404, b"not found", "text/plain")
                return
            payload: dict[str, Any] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                stamp = store.label(str(payload["row_id"]), str(payload["grade"]))
            except (KeyError, ValueError) as exc:
                self._send(400, str(exc).encode(), "text/plain")
                return
            self._send(200, json.dumps({"labelled_at": stamp}).encode(), "application/json")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(paths: Paths, port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(LabelStore(paths)))
    print(f"labelling page: http://127.0.0.1:{port}  (Ctrl+C to stop; every label is saved immediately)")
    server.serve_forever()
