import json
from typing import Dict, Generator, List, Optional

import requests

from .config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, LLM_PROVIDER


class LLMError(RuntimeError):
    pass


def generate_answer(
    question: str,
    evidence: List[Dict[str, object]],
    focus_points: List[str] | None = None,
) -> Dict[str, object]:
    if LLM_PROVIDER == "local":
        return {
            "answer": "Local model not configured yet. Evidence collected below.",
            "confidence": 0.0,
        }
    if not LLM_API_KEY:
        return {
            "answer": "LLM API key not configured. Evidence collected below.",
            "confidence": 0.0,
        }
    prompt = _build_prompt(question, evidence, focus_points=focus_points)
    response = _call_openai_compatible(prompt)
    return response


def generate_answer_stream(
    question: str,
    evidence: List[Dict[str, object]],
    focus_points: List[str] | None = None,
) -> Generator[str, None, None]:
    if LLM_PROVIDER == "local":
        yield "Local model not configured yet. Evidence collected below."
        return
    if not LLM_API_KEY:
        yield "LLM API key not configured. Evidence collected below."
        return

    prompt = _build_prompt(question, evidence, focus_points=focus_points)
    yield from _call_openai_compatible_stream(prompt)


def _call_openai_compatible(prompt: str) -> Dict[str, object]:
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": _build_system_prompt(),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    res = requests.post(
        f"{LLM_API_BASE}/chat/completions", headers=headers, json=payload, timeout=60
    )
    if not res.ok:
        detail = ""
        try:
            data = res.json()
            raw_msg = (
                data.get("error", {}).get("message") if isinstance(data, dict) else None
            )
            if raw_msg:
                detail = str(raw_msg).strip()
        except ValueError:
            detail = res.text.strip()

        if res.status_code in {401, 403}:
            msg = "LLM unauthorized (check LLM_API_KEY and LLM_API_BASE)"
        else:
            msg = f"LLM request failed ({res.status_code})"
        if detail:
            msg = msg + f": {detail}"
        raise LLMError(msg)
    data = res.json()
    content = data["choices"][0]["message"]["content"]
    return {"answer": content, "confidence": 0.6}


def _call_openai_compatible_stream(prompt: str) -> Generator[str, None, None]:
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": _build_system_prompt(),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "stream": True,
    }

    with requests.post(
        f"{LLM_API_BASE}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
        stream=True,
    ) as res:
        if not res.ok:
            detail = ""
            try:
                data = res.json()
                raw_msg = (
                    data.get("error", {}).get("message")
                    if isinstance(data, dict)
                    else None
                )
                if raw_msg:
                    detail = str(raw_msg).strip()
            except ValueError:
                detail = res.text.strip()

            if res.status_code in {401, 403}:
                msg = "LLM unauthorized (check LLM_API_KEY and LLM_API_BASE)"
            else:
                msg = f"LLM request failed ({res.status_code})"
            if detail:
                msg = msg + f": {detail}"
            raise LLMError(msg)

        for line in res.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str.strip() == "[DONE]":
                        return
                    try:
                        data = json.loads(data_str)
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue


def _build_system_prompt() -> str:
    return (
        "Answer based on provided evidence. Be concise. "
        "IMPORTANT: You must respond in the SAME LANGUAGE as the user's question. "
        "If the user asks in Chinese, answer in Chinese. If the user asks in English, answer in English. "
        "Maintain the same language throughout your entire response."
    )


def _build_prompt(
    question: str, evidence: List[Dict[str, object]], focus_points: List[str] | None
) -> str:
    focus_block = ""
    if focus_points:
        cleaned = [str(item).strip() for item in focus_points if str(item).strip()]
        if cleaned:
            focus_block = "\nFocus points:\n" + "\n".join(
                f"- {item}" for item in cleaned
            )
    evidence_lines = []
    for idx, item in enumerate(evidence[:10], start=1):
        evidence_lines.append(_format_evidence(idx, item))
    evidence_block = "\n".join(evidence_lines)
    return (
        f"Question: {question}"
        f"{focus_block}"
        "\n\nEvidence (cite like [E1], [E2]):\n"
        f"{evidence_block}"
        "\n\nInstructions:\n"
        "- Answer using only the evidence above.\n"
        "- If evidence is insufficient, say what is missing.\n"
        "- Include citations like [E1] after relevant sentences."
    )


def _format_evidence(idx: int, item: Dict[str, object]) -> str:
    label = f"E{idx}"
    kind = str(item.get("kind", ""))
    parts = [f"kind={kind}"]

    if item.get("path"):
        parts.append(f"path={item.get('path')}")
    if item.get("line"):
        parts.append(f"line={item.get('line')}")
    if item.get("name"):
        parts.append(f"name={item.get('name')}")
    if (
        item.get("paragraph_index") is not None
        and str(item.get("paragraph_index")).strip() != ""
    ):
        parts.append(f"paragraph={item.get('paragraph_index')}")
    if item.get("page"):
        parts.append(f"page={item.get('page')}")
    if item.get("score") is not None and str(item.get("score")).strip() != "":
        parts.append(f"score={item.get('score')}")
    if (
        item.get("paragraph_confidence") is not None
        and str(item.get("paragraph_confidence")).strip() != ""
    ):
        parts.append(f"paragraph_conf={item.get('paragraph_confidence')}")

    excerpt = item.get("excerpt")
    if not excerpt:
        excerpt = item.get("text_excerpt")
    excerpt_text = str(excerpt or "").strip().replace("\n", " ")
    excerpt_text = excerpt_text[:320]

    return (
        f"[{label}] "
        + " ".join(parts)
        + (f"\nexcerpt: {excerpt_text}\n" if excerpt_text else "\n")
    )
