function normalizeApiBase(value: string): string {
  const trimmed = value.trim();
  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

const API_BASE = (() => {
  const raw = (import.meta as { env?: Record<string, unknown> }).env?.VITE_API_BASE;
  if (typeof raw === "string" && raw.trim()) {
    return normalizeApiBase(raw);
  }
  // Default to same-origin relative paths.
  // This works with Vite dev server proxy when using VSCode port forwarding.
  return "";
})();

function buildUrl(path: string): string {
  if (!path.startsWith("/")) return path;
  return API_BASE ? `${API_BASE}${path}` : path;
}

async function fetchWithFallback(path: string, init?: RequestInit): Promise<Response> {
  const primary = buildUrl(path);
  try {
    return await fetch(primary, init);
  } catch (err) {
    // Don't retry on AbortError - user explicitly cancelled the request
    if (err instanceof Error && err.name === 'AbortError') {
      throw err;
    }
    // If API_BASE is configured but not reachable from the browser (common with VSCode port forwarding),
    // retry same-origin relative path so Vite proxy can forward to backend.
    if (!API_BASE) throw err;
    return await fetch(path, init);
  }
}

let currentAskStreamController: AbortController | null = null;
let currentOverviewStreamController: AbortController | null = null;

export function abortAskProjectStream(): void {
  currentAskStreamController?.abort();
  currentAskStreamController = null;
}

export function abortOverviewStream(): void {
  currentOverviewStreamController?.abort();
  currentOverviewStreamController = null;
}

export type CodeRef = {
  path: string;
  line: number;
  name: string;
  start_line: number;
  end_line: number;
};

export type EvidenceMix = {
  paper_count: number;
  code_count: number;
  total: number;
  paper_pct: number;
  code_pct: number;
};

export type Project = {
  id: string;
  name: string;
  paper_url: string;
  repo_url: string;
  focus_points?: string[] | null;
  doc_urls?: string[] | null;
  created_at: string;
  updated_at: string;
  paper_hash?: string | null;
  repo_hash?: string | null;
  paper_parsed_path?: string | null;
  code_index_path?: string | null;
  alignment_path?: string | null;
  paper_vector_path?: string | null;
  code_vector_path?: string | null;
  paper_bm25_path?: string | null;
  code_bm25_path?: string | null;
};

export async function listProjects(): Promise<Project[]> {
  const res = await fetchWithFallback(`/projects`);
  if (!res.ok) {
    throw new Error("Failed to load projects");
  }
  return res.json();
}

export async function createProject(payload: {
  name?: string;
  paper_url?: string;
  repo_url: string;
  focus_points?: string[];
  doc_urls?: string[];
}): Promise<Project> {
  const res = await fetchWithFallback(`/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let message = "Failed to create project";
    try {
      const errorData = (await res.json()) as { detail?: string };
      if (errorData.detail) {
        message = errorData.detail;
      }
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

export async function getProject(projectId: string): Promise<Project> {
  const res = await fetchWithFallback(`/projects/${projectId}`);
  if (!res.ok) {
    throw new Error("Failed to load project");
  }
  return res.json();
}

export async function ingestProject(projectId: string): Promise<{
  project_id: string;
  paper_hash: string;
  parsed_path: string;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/ingest`, {
    method: "POST",
  });
  if (!res.ok) {
    let message = "Failed to ingest paper";
    try {
      const errorData = await res.json();
      if (errorData.detail) {
        message = errorData.detail;
      }
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

export async function askProject(projectId: string, question: string): Promise<{
  project_id: string;
  question: string;
  answer: string;
  confidence: number;
  created_at: string;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw new Error("Failed to submit question");
  }
  return res.json();
}

export async function askProjectStream(
  projectId: string,
  question: string,
  onChunk: (chunk: string) => void,
  onComplete: (result: {
    answer: string;
    code_refs?: CodeRef[];
    route?: string;
    evidence_mix?: EvidenceMix;
    insufficient_evidence?: boolean;
  }) => void,
  onError: (error: string) => void
): Promise<void>;
export async function askProjectStream(
  projectId: string,
  question: string,
  onChunk: (chunk: string) => void,
  onComplete: (result: {
    answer: string;
    code_refs?: CodeRef[];
    route?: string;
    evidence_mix?: EvidenceMix;
    insufficient_evidence?: boolean;
  }) => void,
  onError: (error: string) => void,
  signal: AbortSignal
): Promise<void>;
export async function askProjectStream(
  projectId: string,
  question: string,
  onChunk: (chunk: string) => void,
  onComplete: (result: {
    answer: string;
    code_refs?: CodeRef[];
    route?: string;
    evidence_mix?: EvidenceMix;
    insufficient_evidence?: boolean;
  }) => void,
  onError: (error: string) => void,
  signal?: AbortSignal
): Promise<void> {
  abortAskProjectStream();
  const controller = new AbortController();
  currentAskStreamController = controller;

  const onAbort = () => controller.abort();
  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", onAbort, { once: true });
  }

  try {
    const res = await fetchWithFallback(`/projects/${projectId}/ask-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error("Failed to start stream");
    }

    let fullAnswer = "";
    let doneCodeRefs: CodeRef[] = [];
    let doneRoute: string | undefined;
    let doneEvidenceMix: EvidenceMix | undefined;
    let doneInsufficientEvidence: boolean | undefined;
    let reportedParseError = false;

    try {
      for await (const evt of iterateSseEvents(res)) {
        let data: {
          chunk?: string;
          done?: boolean;
          answer?: string;
          code_refs?: CodeRef[];
          route?: string;
          evidence_mix?: EvidenceMix;
          insufficient_evidence?: boolean;
          error?: string;
        };
        try {
          data = JSON.parse(evt.data) as {
            chunk?: string;
            done?: boolean;
            answer?: string;
            code_refs?: CodeRef[];
            route?: string;
            evidence_mix?: EvidenceMix;
            insufficient_evidence?: boolean;
            error?: string;
          };
        } catch {
          if (!reportedParseError) {
            reportedParseError = true;
            onError("Malformed stream event (failed to parse SSE data as JSON)");
          }
          continue;
        }

      if (data.chunk) {
        fullAnswer += data.chunk;
        onChunk(data.chunk);
      }

      if (Array.isArray(data.code_refs)) {
        doneCodeRefs = data.code_refs;
      }

      if (typeof data.route === "string") {
        doneRoute = data.route;
      }

      if (data.evidence_mix && typeof data.evidence_mix === "object") {
        doneEvidenceMix = data.evidence_mix;
      }

      if (typeof data.insufficient_evidence === "boolean") {
        doneInsufficientEvidence = data.insufficient_evidence;
      }

      if (data.done) {
        onComplete({
          answer: data.answer || fullAnswer,
          code_refs: doneCodeRefs,
          route: doneRoute,
          evidence_mix: doneEvidenceMix,
          insufficient_evidence: doneInsufficientEvidence,
        });
        return;
      }

      if (data.error) {
        onError(data.error);
        return;
      }
    }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      throw err;
    }

    onComplete({
      answer: fullAnswer,
      code_refs: doneCodeRefs,
      route: doneRoute,
      evidence_mix: doneEvidenceMix,
      insufficient_evidence: doneInsufficientEvidence,
    });
  } finally {
    signal?.removeEventListener("abort", onAbort);
    if (currentAskStreamController === controller) {
      currentAskStreamController = null;
    }
  }
}

type SseEvent = {
  event?: string;
  data: string;
};



function parseSseEvent(rawEvent: string): SseEvent | null {
  const lines = rawEvent.split("\n");
  const dataLines: string[] = [];
  let eventName: string | undefined;

  for (const line of lines) {
    if (line.length === 0) continue;
    if (line.startsWith(":")) continue;

    const colonIdx = line.indexOf(":");
    const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
    let value = colonIdx === -1 ? "" : line.slice(colonIdx + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") {
      eventName = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) return null;
  return { event: eventName, data: dataLines.join("\n") };
}

async function* iterateSseEvents(res: Response): AsyncGenerator<SseEvent, void, void> {
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let pendingCR = false;

  const processChunk = (chunk: string): void => {
    let processed = "";
    let start = 0;
    
    if (pendingCR) {
      if (chunk.length === 0) {
        processed += '\n';
        pendingCR = false;
        start = 0;
      } else if (chunk[0] === '\n') {
        processed += '\n';
        pendingCR = false;
        start = 1;
      } else {
        processed += '\n';
        pendingCR = false;
        start = 0;
      }
    }
    
    for (let i = start; i < chunk.length; i++) {
      const char = chunk[i];
      if (char === '\r') {
        if (i === chunk.length - 1) {
          pendingCR = true;
        } else if (chunk[i + 1] === '\n') {
          processed += '\n';
          i++;
        } else {
          processed += '\n';
        }
      } else if (char === '\n') {
        if (pendingCR) {
          processed += '\n';
          pendingCR = false;
        } else {
          processed += '\n';
        }
      } else {
        if (pendingCR) {
          processed += '\n';
          pendingCR = false;
        }
        processed += char;
      }
    }
    buffer += processed;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      processChunk(chunk);

      while (true) {
        const boundaryIdx = buffer.indexOf("\n\n");
        if (boundaryIdx === -1) break;

        const rawEvent = buffer.slice(0, boundaryIdx);
        buffer = buffer.slice(boundaryIdx + 2);

        if (rawEvent.trim().length === 0) continue;
        const evt = parseSseEvent(rawEvent);
        if (evt) yield evt;
      }
    }

    const finalChunk = decoder.decode();
    if (finalChunk) {
      processChunk(finalChunk);
    }

    if (pendingCR) {
      buffer += '\n';
      pendingCR = false;
    }

    if (buffer.trim().length > 0) {
      const evt = parseSseEvent(buffer);
      if (evt) yield evt;
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Best-effort cancel.
    }
    reader.releaseLock();
  }
}

export async function getQaLog(projectId: string): Promise<{
  project_id: string;
  entries: Array<{
    question: string;
    answer: string;
    route?: string;
    evidence_mix?: EvidenceMix;
    insufficient_evidence?: boolean;
    evidence: Array<{
      paragraph_index?: string;
      page?: string;
      text_excerpt?: string;
      paragraph_confidence?: number;
      kind?: string;
      path?: string;
      name?: string;
      line?: string | number;
      score?: string | number;
      matched_tokens?: string[];
      excerpt?: string;
      doc_id?: string;
    }>;
    code_refs?: CodeRef[];
    confidence: number;
    created_at: string;
  }>;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/qa`);
  if (!res.ok) {
    throw new Error("Failed to load QA log");
  }
  return res.json();
}

export async function indexCode(projectId: string): Promise<{
  project_id: string;
  repo_hash: string;
  index_path: string;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/code-index`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to index code");
  }
  return res.json();
}

export async function alignProject(projectId: string): Promise<{
  project_id: string;
  alignment_path: string;
  match_count: number;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/align`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to align project");
  }
  return res.json();
}

export async function buildVectors(projectId: string): Promise<{
  project_id: string;
  paper_index_path: string;
  code_index_path: string;
  paper_bm25_path: string;
  code_bm25_path: string;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/vector-index`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to build vector indices");
  }
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetchWithFallback(`/projects/${projectId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error("Failed to delete project");
  }
}

export async function getOverview(projectId: string): Promise<{
  project_id: string;
  content: string;
  version: string;
  generated_at: string;
}> {
  const res = await fetchWithFallback(`/projects/${projectId}/overview`);
  if (!res.ok) {
    throw new Error("Failed to load overview");
  }
  return res.json();
}

async function readStream(
  res: Response,
  onChunk: (chunk: string) => void,
  onDone: () => void,
  onError: (error: string) => void
): Promise<void> {
  let reportedParseError = false;

  try {
    for await (const evt of iterateSseEvents(res)) {
      let data: { chunk?: string; done?: boolean; error?: string };
      try {
        data = JSON.parse(evt.data) as { chunk?: string; done?: boolean; error?: string };
      } catch {
        if (!reportedParseError) {
          reportedParseError = true;
          onError("Malformed stream event (failed to parse SSE data as JSON)");
        }
        continue;
      }

      if (data.chunk) {
        onChunk(data.chunk);
      }
      if (data.done) {
        onDone();
        return;
      }
      if (data.error) {
        onError(data.error);
        return;
      }
    }
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      return;
    }
    throw err;
  }
}

export async function generateOverviewQuick(
  projectId: string,
  _lang: string,
  onChunk: (chunk: string) => void,
  onComplete: (version: string) => void,
  onError: (error: string) => void
): Promise<void>;
export async function generateOverviewQuick(
  projectId: string,
  _lang: string,
  onChunk: (chunk: string) => void,
  onComplete: (version: string) => void,
  onError: (error: string) => void,
  signal: AbortSignal
): Promise<void>;
export async function generateOverviewQuick(
  projectId: string,
  _lang: string,
  onChunk: (chunk: string) => void,
  onComplete: (version: string) => void,
  onError: (error: string) => void,
  signal?: AbortSignal
): Promise<void> {
  abortOverviewStream();
  const controller = new AbortController();
  currentOverviewStreamController = controller;

  const onAbort = () => controller.abort();
  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", onAbort, { once: true });
  }

  try {
    const lang = _lang || "zh";
    const encodedLang = encodeURIComponent(lang);
    const res = await fetchWithFallback(
      `/projects/${projectId}/overview/generate-quick?lang=${encodedLang}`,
      {
      method: "POST",
      signal: controller.signal,
      }
    );

    if (!res.ok) {
      throw new Error("Failed to start overview stream");
    }

    await readStream(
      res,
      onChunk,
      () => onComplete("quick"),
      (error) => onError(error)
    );
  } finally {
    signal?.removeEventListener("abort", onAbort);
    if (currentOverviewStreamController === controller) {
      currentOverviewStreamController = null;
    }
  }
}

export async function generateOverviewFull(
  projectId: string,
  _lang: string,
  onChunk: (chunk: string) => void,
  onComplete: (version: string) => void,
  onError: (error: string) => void
): Promise<void>;
export async function generateOverviewFull(
  projectId: string,
  _lang: string,
  onChunk: (chunk: string) => void,
  onComplete: (version: string) => void,
  onError: (error: string) => void,
  signal: AbortSignal
): Promise<void>;
export async function generateOverviewFull(
  projectId: string,
  _lang: string,
  onChunk: (chunk: string) => void,
  onComplete: (version: string) => void,
  onError: (error: string) => void,
  signal?: AbortSignal
): Promise<void> {
  abortOverviewStream();
  const controller = new AbortController();
  currentOverviewStreamController = controller;

  const onAbort = () => controller.abort();
  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", onAbort, { once: true });
  }

  try {
    const lang = _lang || "zh";
    const encodedLang = encodeURIComponent(lang);
    const res = await fetchWithFallback(
      `/projects/${projectId}/overview/generate-full?lang=${encodedLang}`,
      {
      method: "POST",
      signal: controller.signal,
      }
    );

    if (!res.ok) {
      throw new Error("Failed to start overview stream");
    }

    await readStream(
      res,
      onChunk,
      () => onComplete("full"),
      (error) => onError(error)
    );
  } finally {
    signal?.removeEventListener("abort", onAbort);
    if (currentOverviewStreamController === controller) {
      currentOverviewStreamController = null;
    }
  }
}

export async function getCodeFile(projectId: string, path: string): Promise<{
  project_id: string;
  path: string;
  content: string;
  language: string;
}> {
  const encodedPath = encodeURIComponent(path);
  const res = await fetchWithFallback(`/projects/${projectId}/code/file?path=${encodedPath}`);
  if (!res.ok) {
    throw new Error(await readApiErrorDetail(res, "Failed to load code file"));
  }
  return res.json();
}

export async function getCodeSnippet(
  projectId: string,
  path: string,
  startLine: number,
  endLine: number
): Promise<{
  project_id: string;
  path: string;
  content: string;
  language: string;
  start_line: number;
  end_line: number;
}> {
  const encodedPath = encodeURIComponent(path);
  const res = await fetchWithFallback(
    `/projects/${projectId}/code/snippet?path=${encodedPath}&start_line=${startLine}&end_line=${endLine}`
  );
  if (!res.ok) {
    throw new Error(await readApiErrorDetail(res, "Failed to load code snippet"));
  }
  return res.json();
}

async function readApiErrorDetail(res: Response, fallback: string): Promise<string> {
  let message = fallback;
  try {
    const errorData = (await res.json()) as unknown;
    if (errorData && typeof errorData === "object" && "detail" in errorData) {
      const detail = (errorData as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        message = detail;
      }
    }
  } catch {
    // Best-effort parse.
  }
  return message;
}
