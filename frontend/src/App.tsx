import { useEffect, useMemo, useState } from "react";
import {
  askProject,
  alignProject,
  buildVectors,
  createProject,
  getProject,
  getQaLog,
  getSummary,
  indexCode,
  ingestProject,
  listProjects,
  Project,
} from "./api";

type SummaryState = { text: string; error?: string };

export default function App() {
  const [lang, setLang] = useState<"zh" | "en">("zh");
  const [guideOpen, setGuideOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<SummaryState>({ text: "" });
  const [qaLog, setQaLog] = useState<
    Array<{
      question: string;
      answer: string;
      created_at: string;
      evidence?: Array<{
        kind?: string;
        path?: string;
        name?: string;
        line?: string;
        score?: number;
        paragraph_confidence?: number;
        excerpt?: string;
      }>;
    }>
  >([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ name: "", paper_url: "", repo_url: "", focus_points: "" });
  const [error, setError] = useState<string | null>(null);

  const copy = {
    zh: {
      eyebrow: "\u8bba\u6587\u4ee3\u7801\u5bf9\u7167",
      title: "\u9879\u76ee\u5de5\u4f5c\u53f0",
      projects: "\u9879\u76ee",
      create: "\u521b\u5efa\u9879\u76ee",
      projectName: "\u9879\u76ee\u540d\u79f0",
      paperUrl: "\u8bba\u6587\u94fe\u63a5",
      repoUrl: "GitHub \u94fe\u63a5",
      focusPoints: "\u5173\u6ce8\u70b9\uff08\u9017\u53f7\u5206\u9694\uff09",
      createBtn: "\u521b\u5efa\u9879\u76ee",
      detail: "\u9879\u76ee\u8be6\u60c5",
      ingest: "\u89e3\u6790\u8bba\u6587",
      indexCode: "\u7d22\u5f15\u4ee3\u7801",
      align: "\u5bf9\u7167",
      buildVectors: "\u6784\u5efa\u5411\u91cf",
      project: "\u9879\u76ee",
      paperHash: "\u8bba\u6587\u54c8\u5e0c",
      repoHash: "\u4ed3\u5e93\u54c8\u5e0c",
      alignment: "\u5bf9\u7167\u6587\u4ef6",
      summary: "\u9879\u76ee\u6c89\u6dc0",
      ask: "\u8be2\u95ee",
      question: "\u95ee\u9898",
      submit: "\u63d0\u4ea4\u95ee\u9898",
      emptyProjects: "\u6682\u65e0\u9879\u76ee",
      selectProject: "\u8bf7\u9009\u62e9\u9879\u76ee\u67e5\u770b\u8be6\u60c5\u3002",
      noSummary: "\u6682\u65e0\u6c89\u6dc0\u5185\u5bb9\u3002",
      noQuestions: "\u6682\u65e0\u95ee\u7b54\u3002",
      working: "\u5904\u7406\u4e2d...",
      guideTitle: "\u4f7f\u7528\u6307\u5357",
      guideToggle: "\u70b9\u51fb\u67e5\u770b\u6216\u6536\u8d77",
      guideSteps: [
        "1. \u521b\u5efa\u9879\u76ee\uff1a\u8f93\u5165\u8bba\u6587\u548c\u4ed3\u5e93\u94fe\u63a5\u3002",
        "2. \u70b9\u51fb\u89e3\u6790\u8bba\u6587\uff0c\u751f\u6210\u6bb5\u843d\u7ed3\u6784\u3002",
        "3. \u7d22\u5f15\u4ee3\u7801\uff0c\u751f\u6210\u6587\u4ef6\u3001\u7b26\u53f7\u548c\u6587\u672c\u7d22\u5f15\u3002",
        "4. \u5bf9\u7167\u7ed3\u679c\u7528\u4e8e\u627e\u5230\u6bb5\u843d\u4e0e\u4ee3\u7801\u8fde\u63a5\u3002",
        "5. \u6784\u5efa\u5411\u91cf\u7528\u4e8e\u68c0\u7d22\u6587\u672c\u3002",
        "6. \u63d0\u4ea4\u95ee\u9898\uff0c\u4f1a\u4fdd\u5b58\u95ee\u7b54\u548c\u8bc1\u636e\u3002",
      ],
    },
    en: {
      eyebrow: "Paper + Code Alignment",
      title: "Project Workspace",
      projects: "Projects",
      create: "Create Project",
      projectName: "Project name",
      paperUrl: "Paper URL",
      repoUrl: "GitHub URL",
      focusPoints: "Focus points (comma separated)",
      createBtn: "Create project",
      detail: "Project Detail",
      ingest: "Ingest paper",
      indexCode: "Index code",
      align: "Align",
      buildVectors: "Build vectors",
      project: "Project",
      paperHash: "Paper hash",
      repoHash: "Repo hash",
      alignment: "Alignment",
      summary: "Project Summary",
      ask: "Ask a Question",
      question: "Question",
      submit: "Submit question",
      emptyProjects: "No projects yet.",
      selectProject: "Select a project to view details.",
      noSummary: "No summary yet.",
      noQuestions: "No questions yet.",
      working: "Working...",
      guideTitle: "Usage Guide",
      guideToggle: "Click to expand or collapse",
      guideSteps: [
        "1. Create a project with paper and repo URLs.",
        "2. Ingest the paper to parse paragraphs.",
        "3. Index the code for files, symbols, and text.",
        "4. Align to link paragraphs with code.",
        "5. Build vectors for retrieval.",
        "6. Ask questions and persist evidence.",
      ],
    },
  } as const;

  const t = copy[lang];

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
      setQaLog([]);
      return;
    }
    setLoading(true);
    Promise.all([getProject(selectedId), getSummary(selectedId), getQaLog(selectedId)])
      .then(([project, summaryResp, qaResp]) => {
        setSelectedProject(project);
        setSummary({ text: summaryResp.summary || "" });
        setQaLog(qaResp.entries || []);
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
      const qaResp = await getQaLog(selectedId);
      setSelectedProject(project);
      setSummary({ text: summaryResp.summary || "" });
      setQaLog(qaResp.entries || []);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleIndexCode() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      await indexCode(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId || !question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await askProject(selectedId, question.trim());
      const summaryResp = await getSummary(selectedId);
      const qaResp = await getQaLog(selectedId);
      setSummary({ text: summaryResp.summary || "" });
      setQaLog(qaResp.entries || []);
      setQuestion("");
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleAlign() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      await alignProject(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleBuildVectors() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      await buildVectors(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
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
          <p className="eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
        </div>
        <div className="status">
          <span>{projects.length} {t.projects.toLowerCase()}</span>
        </div>
        <div className="lang-toggle">
          <button
            className="toggle"
            onClick={() => setLang(lang === "zh" ? "en" : "zh")}
          >
            {lang === "zh" ? "\u4e2d\u6587 / EN" : "EN / \u4e2d\u6587"}
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <h2>{t.projects}</h2>
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
            {projects.length === 0 && <div className="empty">{t.emptyProjects}</div>}
          </div>
        </aside>

        <main className="main">
          <section className="card">
            <h2>{t.create}</h2>
            <form className="form" onSubmit={handleCreate}>
              <label>
                {t.projectName}
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="LTX2 analysis"
                  required
                />
              </label>
              <label>
                {t.paperUrl}
                <input
                  value={form.paper_url}
                  onChange={(e) => setForm({ ...form, paper_url: e.target.value })}
                  placeholder="https://arxiv.org/abs/xxxx"
                  required
                />
              </label>
              <label>
                {t.repoUrl}
                <input
                  value={form.repo_url}
                  onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
                  placeholder="https://github.com/org/repo"
                  required
                />
              </label>
              <label>
                {t.focusPoints}
                <input
                  value={form.focus_points}
                  onChange={(e) => setForm({ ...form, focus_points: e.target.value })}
                  placeholder="positional encoding, loss, sampler"
                />
              </label>
              <button type="submit" className="primary">
                {t.createBtn}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="card-header">
              <h2>{t.guideTitle}</h2>
              <button className="ghost" onClick={() => setGuideOpen(!guideOpen)}>
                {t.guideToggle}
              </button>
            </div>
            {guideOpen && (
              <div className="guide">
                {t.guideSteps.map((step) => (
                  <p key={step}>{step}</p>
                ))}
              </div>
            )}
          </section>

          <section className="card">
            <div className="card-header">
              <h2>{t.detail}</h2>
              <div className="button-row">
                <button className="ghost" onClick={handleIngest} disabled={!selectedId || loading}>
                  {loading ? t.working : t.ingest}
                </button>
                <button className="ghost" onClick={handleIndexCode} disabled={!selectedId || loading}>
                  {loading ? t.working : t.indexCode}
                </button>
                <button className="ghost" onClick={handleAlign} disabled={!selectedId || loading}>
                  {loading ? t.working : t.align}
                </button>
                <button className="ghost" onClick={handleBuildVectors} disabled={!selectedId || loading}>
                  {loading ? t.working : t.buildVectors}
                </button>
              </div>
            </div>
            {selectedProject ? (
              <div className="detail-grid">
                <div>
                  <p className="label">{t.project}</p>
                  <p>{selectedProject.name}</p>
                </div>
                <div>
                  <p className="label">{t.paperUrl}</p>
                  <p className="mono">{selectedProject.paper_url}</p>
                </div>
                <div>
                  <p className="label">{t.repoUrl}</p>
                  <p className="mono">{selectedProject.repo_url}</p>
                </div>
                <div>
                  <p className="label">{t.paperHash}</p>
                  <p className="mono">{selectedProject.paper_hash || "-"}</p>
                </div>
                <div>
                  <p className="label">{t.repoHash}</p>
                  <p className="mono">{selectedProject.repo_hash || "-"}</p>
                </div>
                <div>
                  <p className="label">{t.alignment}</p>
                  <p className="mono">{selectedProject.alignment_path || "-"}</p>
                </div>
              </div>
            ) : (
              <p className="empty">{t.selectProject}</p>
            )}
          </section>

          <section className="card">
            <h2>{t.summary}</h2>
            <div className="summary">
              {summary.text ? <pre>{summary.text}</pre> : <p className="empty">{t.noSummary}</p>}
            </div>
          </section>

          <section className="card">
            <h2>{t.ask}</h2>
            <form className="form" onSubmit={handleAsk}>
              <label>
                {t.question}
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="What positional encoding is used and why?"
                />
              </label>
              <button type="submit" className="primary" disabled={!selectedId || loading}>
                {loading ? t.working : t.submit}
              </button>
            </form>
            <div className="qa-log">
              {qaLog.length === 0 && <p className="empty">{t.noQuestions}</p>}
              {qaLog.map((entry, index) => (
                <div className="qa-entry" key={`${entry.created_at}-${index}`}>
                  <p className="label">Q</p>
                  <p>{entry.question}</p>
                  <p className="label">A</p>
                  <p>{entry.answer}</p>
                  {entry.evidence && entry.evidence.length > 0 && (
                    <div className="qa-evidence">
                      <p className="label">Evidence</p>
                      <ul>
                        {entry.evidence.slice(0, 3).map((ev, evIndex) => (
                          <li key={`${ev.path}-${evIndex}`}>
                            <span className="mono">{ev.path || "unknown"}</span>
                            {ev.name ? ` :: ${ev.name}` : ""}
                            {ev.line ? ` (L${ev.line})` : ""}
                            {typeof ev.score === "number" ? ` score ${ev.score}` : ""}
                            {typeof ev.paragraph_confidence === "number"
                              ? ` conf ${ev.paragraph_confidence.toFixed(2)}`
                              : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="qa-time">{new Date(entry.created_at).toLocaleString()}</p>
                </div>
              ))}
            </div>
          </section>

          {error && <div className="error">{error}</div>}
        </main>
      </div>
    </div>
  );
}
