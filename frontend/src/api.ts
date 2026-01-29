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
