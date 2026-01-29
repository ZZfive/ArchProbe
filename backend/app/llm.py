import json
from typing import Dict, List

import requests

from .config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, LLM_PROVIDER


class LLMError(RuntimeError):
    pass


def generate_answer(
    question: str, evidence: List[Dict[str, object]]
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
    prompt = _build_prompt(question, evidence)
    response = _call_openai_compatible(prompt)
    return response


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
                "content": "Answer based on provided evidence. Be concise.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    res = requests.post(
        f"{LLM_API_BASE}/chat/completions", headers=headers, json=payload, timeout=60
    )
    if not res.ok:
        raise LLMError(f"LLM request failed: {res.status_code}")
    data = res.json()
    content = data["choices"][0]["message"]["content"]
    return {"answer": content, "confidence": 0.6}


def _build_prompt(question: str, evidence: List[Dict[str, object]]) -> str:
    evidence_lines = []
    for item in evidence[:10]:
        evidence_lines.append(json.dumps(item, ensure_ascii=True))
    evidence_block = "\n".join(evidence_lines)
    return f"Question: {question}\nEvidence:\n{evidence_block}\nAnswer with cited evidence."
