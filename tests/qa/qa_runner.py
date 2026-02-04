#!/usr/bin/env python3
import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request


def _iter_sse_events(resp):
    buf = []
    while True:
        line = resp.readline()
        if not line:
            if buf:
                yield buf
            return
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            text = line.decode("utf-8", errors="replace")

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text == "\n":
            if buf:
                yield buf
                buf = []
            continue
        buf.append(text)


def _parse_sse_data(lines):
    data_lines = []
    for line in lines:
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value.rstrip("\n"))
    if not data_lines:
        return None
    return "\n".join(data_lines)


def ask_stream(api_base, project_id, question, timeout_s=120):
    url = f"{api_base.rstrip('/')}/projects/{project_id}/ask-stream"
    body = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    chunks = []
    final = None
    errors = []
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            for event_lines in _iter_sse_events(resp):
                data = _parse_sse_data(event_lines)
                if not data:
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if isinstance(payload, dict) and payload.get("chunk"):
                    chunks.append(str(payload.get("chunk")))

                if isinstance(payload, dict) and payload.get("error"):
                    errors.append(str(payload.get("error")))
                    break

                if isinstance(payload, dict) and payload.get("done"):
                    final = payload
                    break
    except urllib.error.HTTPError as err:
        try:
            raw = err.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        raise RuntimeError(f"HTTP error {err.code}: {raw.strip()}")
    except urllib.error.URLError as err:
        raise RuntimeError(f"Request failed: {err}")

    if final is None:
        final = {}
    answer = str(final.get("answer") or "".join(chunks))
    return {
        "answer": answer,
        "done_payload": final,
        "errors": errors,
    }


def main(argv):
    parser = argparse.ArgumentParser(
        description="Run a small QA set against /ask-stream"
    )
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", dest="out_path", required=True)
    args = parser.parse_args(argv)

    with open(args.in_path, "r", encoding="utf-8") as f:
        qa = json.load(f)
    items = qa.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Invalid QA set: missing items[]")

    started_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    results = {
        "project_id": args.project_id,
        "api_base": args.api_base,
        "started_at": started_at,
        "items": [],
    }

    for item in items:
        qid = str(item.get("id", ""))
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        expected_route = str(item.get("expected_route", ""))
        try:
            resp = ask_stream(args.api_base, args.project_id, question)
            done = resp.get("done_payload") or {}
            results["items"].append(
                {
                    "id": qid,
                    "question": question,
                    "expected_route": expected_route,
                    "route": done.get("route"),
                    "evidence_mix": done.get("evidence_mix"),
                    "insufficient_evidence": done.get("insufficient_evidence"),
                    "answer": resp.get("answer", ""),
                    "code_refs": done.get("code_refs"),
                    "evidence": done.get("evidence"),
                    "error": (resp.get("errors") or [None])[0],
                }
            )
        except Exception as err:
            results["items"].append(
                {
                    "id": qid,
                    "question": question,
                    "expected_route": expected_route,
                    "route": None,
                    "evidence_mix": None,
                    "insufficient_evidence": None,
                    "answer": "",
                    "code_refs": None,
                    "evidence": None,
                    "error": str(err),
                }
            )

    out_dir = os.path.dirname(args.out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=True, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
