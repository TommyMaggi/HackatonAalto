#!/usr/bin/env python3
"""Local server for the operator UI.

Serves the repo as static files — so ui/index.html's relative fetches to
../artifacts/*.json keep working exactly as with `python3 -m http.server` —
and adds the one write path the UI needs: POST /api/decision. That is the
only place the operator UI is allowed to mutate state on disk.

    python3 ui/server.py [port]

Then open http://localhost:8000/ui/

An "accept" or "contest" only appends to the decision log. An "override"
does two things together: it appends a decision_log entry of kind
"override" (via trust.decision_log.DecisionLog) AND writes the
human_override field on the matching inference in artifacts/semantics.json,
validated against contracts/semantics.schema.json before the write lands.
The original `role` is never touched — human_override sits beside it as the
audit trail the schema already defines.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trust.decision_log import DecisionLog  # noqa: E402

SEMANTICS_PATH = ROOT / "artifacts" / "semantics.json"
SCHEMA_PATH = ROOT / "contracts" / "semantics.schema.json"
DECISION_LOG_PATH = ROOT / "artifacts" / "decision_log.jsonl"
# The decision log screen (ui/decision_log.html) reads the example decision
# log, not the live one that override actions from the sensor report append
# to. The egress panel summarizes the same file the table below it shows.
EXAMPLES_DECISION_LOG_PATH = ROOT / "artifacts" / "examples" / "decision_log.jsonl"

VALID_ACTIONS = {"accept", "contest", "override"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_semantics(doc: dict) -> None:
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(doc, schema)


def _load_semantics() -> dict:
    if not SEMANTICS_PATH.exists():
        raise FileNotFoundError(f"{SEMANTICS_PATH} does not exist. Run `make setup` first.")
    return json.loads(SEMANTICS_PATH.read_text())


def _write_semantics_atomic(doc: dict) -> None:
    tmp = SEMANTICS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(SEMANTICS_PATH)


def _find_inference(doc: dict, col_id: str) -> dict:
    """Locate one inference, whichever shape semantics.json is in.

    Form A: {"inferences": [{"col_id": "col_012", ...}, ...]}
    Form B: {"col_012": {...}, ...}   <- what the pipeline stages emit

    Returns the dict itself, so the caller's mutation lands in `doc` and gets
    written back. Added 19 Sep during integration.
    """
    for inf in doc.get("inferences", []) or []:
        if inf.get("col_id") == col_id:
            return inf

    node = doc.get(col_id)
    if isinstance(node, dict):
        return node

    raise ValueError(f"no inference for {col_id!r} in {SEMANTICS_PATH.name}")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/egress_summary":
            try:
                log = DecisionLog(path=EXAMPLES_DECISION_LOG_PATH)
                self._send_json(200, log.egress_summary())
            except Exception as exc:
                self._send_json(500, {"error": f"internal error: {exc}"})
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/decision":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return

        try:
            result = self._handle_decision(body)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception as exc:  # still JSON to the browser, never a stack trace
            self._send_json(500, {"error": f"internal error: {exc}"})
            return

        self._send_json(200, result)

    def _handle_decision(self, body: dict) -> dict:
        col_id = body.get("col_id")
        action = body.get("action")
        by = (body.get("by") or "").strip()
        rationale = (body.get("rationale") or "").strip()

        if not col_id:
            raise ValueError("col_id is required")
        if action not in VALID_ACTIONS:
            raise ValueError(f"action must be one of {sorted(VALID_ACTIONS)}")
        if not by:
            raise ValueError("by (operator name) is required")

        log = DecisionLog(path=DECISION_LOG_PATH)

        if action == "accept":
            entry_id = log.append(
                stage="S4_semantics",
                kind="human_review",
                summary=f"Operator accepted the inferred role for {col_id}.",
                actor_type="human",
                actor_name=by,
                subject=[col_id],
            )
            return {"entry_id": entry_id}

        if action == "contest":
            if not rationale:
                raise ValueError("rationale is required to contest")
            entry_id = log.append(
                stage="S4_semantics",
                kind="human_review",
                summary=f"Operator contested the inferred role for {col_id}: {rationale}",
                actor_type="human",
                actor_name=by,
                subject=[col_id],
            )
            return {"entry_id": entry_id}

        # action == "override"
        new_role = (body.get("role") or "").strip()
        if not new_role:
            raise ValueError("role is required to override")
        if not rationale:
            raise ValueError("rationale is required to override")

        doc = _load_semantics()
        inf = _find_inference(doc, col_id)
        # Form A calls it "role", Form B calls it "inferred_role".
        original_role = inf.get("role") or inf.get("inferred_role")

        entry_id = log.append(
            stage="S4_semantics",
            kind="override",
            summary=f"Operator overrode the inferred role for {col_id}.",
            actor_type="human",
            actor_name=by,
            subject=[col_id],
            override={
                "target": f"semantics/{col_id}/role",
                "from": original_role,
                "to": new_role,
                "rationale": rationale,
            },
        )

        inf["human_override"] = {
            "role": new_role,
            "by": by,
            "at": _now(),
            "rationale": rationale,
        }

        _validate_semantics(doc)
        _write_semantics_atomic(doc)

        return {"entry_id": entry_id, "inference": inf}


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"serving {ROOT} on http://localhost:{port}/  (operator UI: http://localhost:{port}/ui/)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
