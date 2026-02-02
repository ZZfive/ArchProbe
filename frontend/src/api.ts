const API_BASE = "http://localhost:8000";

export type Project = {
  id: string;
  name: string;
  paper_url: string;
  repo_url: string;
  focus_points?: string[] | null;
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
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) {
    throw new Error("Failed to load projects");
  }
  return res.json();
}

export async function createProject(payload: {
  name: string;
  paper_url: string;
  repo_url: string;
  focus_points?: string[];
}): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error("Failed to create project");
  }
  return res.json();
}

export async function getProject(projectId: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`);
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
  const res = await fetch(`${API_BASE}/projects/${projectId}/ingest`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to ingest paper");
  }
  return res.json();
}

export async function getSummary(projectId: string): Promise<{
  project_id: string;
  summary: string;
}> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/summary`);
  if (!res.ok) {
    throw new Error("Failed to load summary");
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
  const res = await fetch(`${API_BASE}/projects/${projectId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw new Error("Failed to submit question");
  }
  return res.json();
}

export async function getQaLog(projectId: string): Promise<{
  project_id: string;
  entries: Array<{
    question: string;
    answer: string;
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
    confidence: number;
    created_at: string;
  }>;
}> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/qa`);
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
  const res = await fetch(`${API_BASE}/projects/${projectId}/code-index`, {
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
  const res = await fetch(`${API_BASE}/projects/${projectId}/align`, {
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
  const res = await fetch(`${API_BASE}/projects/${projectId}/vector-index`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to build vector indices");
  }
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error("Failed to delete project");
  }
}
