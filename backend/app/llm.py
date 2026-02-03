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


def generate_overview_stream(
    project_name: str,
    paper_url: str,
    repo_url: str,
    readme_content: str,
    paper_abstract: str,
    focus_points: List[str] | None,
    lang: str = "zh",
) -> Generator[str, None, None]:
    if LLM_PROVIDER == "local":
        yield "Local model not configured yet."
        return
    if not LLM_API_KEY:
        yield "LLM API key not configured."
        return

    prompt = _build_overview_prompt(
        project_name,
        paper_url,
        repo_url,
        readme_content,
        paper_abstract,
        focus_points,
        lang,
    )
    system_prompt = _build_overview_system_prompt(lang)
    yield from _call_openai_compatible_stream_with_system(prompt, system_prompt)


def generate_overview_full_stream(
    project_name: str,
    paper_url: str,
    repo_url: str,
    readme_content: str,
    paper_paragraphs: List[str],
    code_symbols: List[Dict[str, str]],
    focus_points: List[str] | None,
    lang: str = "zh",
) -> Generator[str, None, None]:
    if LLM_PROVIDER == "local":
        yield "Local model not configured yet."
        return
    if not LLM_API_KEY:
        yield "LLM API key not configured."
        return

    prompt = _build_overview_full_prompt(
        project_name,
        paper_url,
        repo_url,
        readme_content,
        paper_paragraphs,
        code_symbols,
        focus_points,
        lang,
    )
    system_prompt = _build_overview_system_prompt(lang)
    yield from _call_openai_compatible_stream_with_system(prompt, system_prompt)


def _call_openai_compatible_stream_with_system(
    prompt: str, system_prompt: str
) -> Generator[str, None, None]:
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
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


def _build_overview_system_prompt(lang: str) -> str:
    if lang == "zh":
        return (
            "你是一位专业的技术文档撰写专家。请基于提供的论文和代码仓库信息，"
            "生成一份详细的项目概览，包含项目背景、核心创新点、技术实现特点等内容。"
            "使用中文撰写，保持专业且易懂的语气。"
        )
    return (
        "You are a professional technical documentation expert. Based on the provided "
        "paper and code repository information, generate a detailed project overview "
        "including project background, core innovations, and technical implementation "
        "highlights. Write in English with a professional yet accessible tone."
    )


def _build_overview_prompt(
    project_name: str,
    paper_url: str,
    repo_url: str,
    readme_content: str,
    paper_abstract: str,
    focus_points: List[str] | None,
    lang: str,
) -> str:
    focus_block = ""
    if focus_points:
        cleaned = [str(item).strip() for item in focus_points if str(item).strip()]
        if cleaned:
            if lang == "zh":
                focus_block = "\n关注点：\n" + "\n".join(
                    f"- {item}" for item in cleaned
                )
            else:
                focus_block = "\nFocus points:\n" + "\n".join(
                    f"- {item}" for item in cleaned
                )

    if lang == "zh":
        return (
            f"项目名称：{project_name}\n"
            f"论文链接：{paper_url}\n"
            f"代码仓库：{repo_url}{focus_block}\n\n"
            "【论文摘要】\n"
            f"{paper_abstract}\n\n"
            "【README内容】\n"
            f"{readme_content[:3000]}\n\n"
            "请生成一份项目概览，包含以下部分：\n"
            "## 项目简介\n"
            "简要介绍项目的背景和目标。\n\n"
            "## 核心创新点\n"
            "总结论文和代码中的主要创新之处。\n\n"
            "## 技术架构\n"
            "基于README描述的技术栈和架构设计。\n\n"
            "## 关键特性\n"
            "列出项目的主要功能特性。"
        )
    return (
        f"Project Name: {project_name}\n"
        f"Paper URL: {paper_url}\n"
        f"Repository: {repo_url}{focus_block}\n\n"
        "[Paper Abstract]\n"
        f"{paper_abstract}\n\n"
        "[README Content]\n"
        f"{readme_content[:3000]}\n\n"
        "Please generate a project overview with the following sections:\n"
        "## Project Introduction\n"
        "Brief background and goals.\n\n"
        "## Core Innovations\n"
        "Main innovations from the paper and code.\n\n"
        "## Technical Architecture\n"
        "Tech stack and architecture based on README.\n\n"
        "## Key Features\n"
        "Main functionality and capabilities."
    )


def _build_overview_full_prompt(
    project_name: str,
    paper_url: str,
    repo_url: str,
    readme_content: str,
    paper_paragraphs: List[str],
    code_symbols: List[Dict[str, str]],
    focus_points: List[str] | None,
    lang: str,
) -> str:
    focus_block = ""
    if focus_points:
        cleaned = [str(item).strip() for item in focus_points if str(item).strip()]
        if cleaned:
            if lang == "zh":
                focus_block = "\n关注点：\n" + "\n".join(
                    f"- {item}" for item in cleaned
                )
            else:
                focus_block = "\nFocus points:\n" + "\n".join(
                    f"- {item}" for item in cleaned
                )

    paper_content = "\n\n".join(paper_paragraphs[:20])

    symbol_summary = ""
    if code_symbols:
        classes = [s for s in code_symbols if s.get("type") == "class"][:10]
        functions = [s for s in code_symbols if s.get("type") in ("def", "function")][
            :15
        ]
        if lang == "zh":
            symbol_summary = "\n主要类：\n" + "\n".join(
                f"- {c.get('name', '')} ({c.get('path', '')})" for c in classes
            )
            symbol_summary += "\n主要函数：\n" + "\n".join(
                f"- {f.get('name', '')} ({f.get('path', '')})" for f in functions
            )
        else:
            symbol_summary = "\nMain Classes:\n" + "\n".join(
                f"- {c.get('name', '')} ({c.get('path', '')})" for c in classes
            )
            symbol_summary += "\nMain Functions:\n" + "\n".join(
                f"- {f.get('name', '')} ({f.get('path', '')})" for f in functions
            )

    if lang == "zh":
        return (
            f"项目名称：{project_name}\n"
            f"论文链接：{paper_url}\n"
            f"代码仓库：{repo_url}{focus_block}\n\n"
            "【完整论文内容】\n"
            f"{paper_content[:5000]}\n\n"
            "【README内容】\n"
            f"{readme_content[:3000]}\n\n"
            "【代码结构摘要】\n"
            f"{symbol_summary}\n\n"
            "请生成一份详细的项目概览，包含以下部分：\n"
            "## 项目简介\n"
            "项目的背景、目标和应用场景。\n\n"
            "## 核心创新点\n"
            "论文的理论创新和技术突破。\n\n"
            "## 技术实现细节\n"
            "基于代码实现的架构设计、关键算法和数据流。\n\n"
            "## 主要组件\n"
            "核心类和模块的功能说明。\n\n"
            "## 使用场景\n"
            "适用的问题类型和应用领域。\n\n"
            "## 性能特点\n"
            "效率、扩展性等性能相关特性（如有提及）。"
        )
    return (
        f"Project Name: {project_name}\n"
        f"Paper URL: {paper_url}\n"
        f"Repository: {repo_url}{focus_block}\n\n"
        "[Full Paper Content]\n"
        f"{paper_content[:5000]}\n\n"
        "[README Content]\n"
        f"{readme_content[:3000]}\n\n"
        "[Code Structure Summary]\n"
        f"{symbol_summary}\n\n"
        "Please generate a detailed project overview with:\n"
        "## Project Introduction\n"
        "Background, goals, and application scenarios.\n\n"
        "## Core Innovations\n"
        "Theoretical contributions and technical breakthroughs.\n\n"
        "## Technical Implementation\n"
        "Architecture, key algorithms, and data flow based on code.\n\n"
        "## Main Components\n"
        "Core classes and modules with functionality.\n\n"
        "## Use Cases\n"
        "Applicable problem types and domains.\n\n"
        "## Performance Characteristics\n"
        "Efficiency, scalability, and other performance traits."
    )
