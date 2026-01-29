import { useEffect, useMemo, useState } from "react";
import {
  createProject,
  getProject,
  getSummary,
  ingestProject,
  listProjects,
  Project,
} from "./api";

type SummaryState = { text: string; error?: string };

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<SummaryState>({ text: "" });
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ name: "", paper_url: "", repo_url: "", focus_points: "" });
  const [error, setError] = useState<string | null>(null);

  const focusPoints = useMemo(() => {
    const trimmed = form.focus_points.trim();
    if (!trimmed) return [];
    return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
  }, [form.focus_points]);

  async function refreshProjects() {
    const data = await listProjects();
    setProjects(data);
    if (!selectedId && data.length > 0) {
      setSelectedId(data[0].id);
    }
  }

  useEffect(() => {
    refreshProjects().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setSelectedProject(null);
      setSummary({ text: "" });
      return;
    }
    setLoading(true);
    Promise.all([getProject(selectedId), getSummary(selectedId)])
      .then(([project, summaryResp]) => {
        setSelectedProject(project);
        setSummary({ text: summaryResp.summary || "" });
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, [selectedId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await createProject({
        name: form.name.trim(),
        paper_url: form.paper_url.trim(),
        repo_url: form.repo_url.trim(),
        focus_points: focusPoints,
      });
      setForm({ name: "", paper_url: "", repo_url: "", focus_points: "" });
      await refreshProjects();
      setSelectedId(created.id);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    }
  }

  async function handleIngest() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      await ingestProject(selectedId);
      const project = await getProject(selectedId);
      const summaryResp = await getSummary(selectedId);
      setSelectedProject(project);
      setSummary({ text: summaryResp.summary || "" });
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <p className="eyebrow">Paper + Code Alignment</p>
          <h1>Project Workspace</h1>
        </div>
        <div className="status">
          <span>{projects.length} projects</span>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <h2>Projects</h2>
          <div className="project-list">
            {projects.map((project) => (
              <button
                key={project.id}
                className={project.id === selectedId ? "project active" : "project"}
                onClick={() => setSelectedId(project.id)}
              >
                <div className="project-name">{project.name}</div>
                <div className="project-meta">{project.paper_url}</div>
              </button>
            ))}
            {projects.length === 0 && <div className="empty">No projects yet.</div>}
          </div>
        </aside>

        <main className="main">
          <section className="card">
            <h2>Create Project</h2>
            <form className="form" onSubmit={handleCreate}>
              <label>
                Project name
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="LTX2 analysis"
                  required
                />
              </label>
              <label>
                Paper URL
                <input
                  value={form.paper_url}
                  onChange={(e) => setForm({ ...form, paper_url: e.target.value })}
                  placeholder="https://arxiv.org/abs/xxxx"
                  required
                />
              </label>
              <label>
                GitHub URL
                <input
                  value={form.repo_url}
                  onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
                  placeholder="https://github.com/org/repo"
                  required
                />
              </label>
              <label>
                Focus points (comma separated)
                <input
                  value={form.focus_points}
                  onChange={(e) => setForm({ ...form, focus_points: e.target.value })}
                  placeholder="positional encoding, loss, sampler"
                />
              </label>
              <button type="submit" className="primary">
                Create project
              </button>
            </form>
          </section>

          <section className="card">
            <div className="card-header">
              <h2>Project Detail</h2>
              <button className="ghost" onClick={handleIngest} disabled={!selectedId || loading}>
                {loading ? "Working..." : "Ingest paper"}
              </button>
            </div>
            {selectedProject ? (
              <div className="detail-grid">
                <div>
                  <p className="label">Project</p>
                  <p>{selectedProject.name}</p>
                </div>
                <div>
                  <p className="label">Paper URL</p>
                  <p className="mono">{selectedProject.paper_url}</p>
                </div>
                <div>
                  <p className="label">Repo URL</p>
                  <p className="mono">{selectedProject.repo_url}</p>
                </div>
                <div>
                  <p className="label">Paper hash</p>
                  <p className="mono">{selectedProject.paper_hash || "-"}</p>
                </div>
              </div>
            ) : (
              <p className="empty">Select a project to view details.</p>
            )}
          </section>

          <section className="card">
            <h2>Project Summary</h2>
            <div className="summary">
              {summary.text ? <pre>{summary.text}</pre> : <p className="empty">No summary yet.</p>}
            </div>
          </section>

          {error && <div className="error">{error}</div>}
        </main>
      </div>
    </div>
  );
}
