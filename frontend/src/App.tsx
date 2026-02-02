import { useEffect, useMemo, useRef, useState } from "react";
import {
  askProject,
  alignProject,
  buildVectors,
  createProject,
  deleteProject,
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
  const [createOpen, setCreateOpen] = useState(false);
  const [createStep, setCreateStep] = useState<1 | 2>(1);
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
        line?: string | number;
        score?: string | number;
        paragraph_confidence?: number;
        excerpt?: string;
        paragraph_index?: string;
        page?: string;
        text_excerpt?: string;
        doc_id?: string;
      }>;
    }>
  >([]);
  const [question, setQuestion] = useState("");
  const [loadingProject, setLoadingProject] = useState(false);
  const [busyAction, setBusyAction] = useState<
    null | "create" | "delete" | "ingest" | "index" | "align" | "vectors" | "ask"
  >(null);
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
      done: "\u5df2\u5b8c\u6210",
      pipelineHint:
        "\u8bf7\u6309 1\u21922\u21923\u21924 \u7684\u987a\u5e8f\u6267\u884c\u3002\u5df2\u5b8c\u6210\u7684\u6b65\u9aa4\u4f1a\u81ea\u52a8\u7981\u7528\uff0c\u907f\u514d\u91cd\u590d\u6267\u884c\u3002",
      deleteProject: "\u5220\u9664\u9879\u76ee",
      deleteConfirm:
        "\u786e\u5b9a\u5220\u9664\u8be5\u9879\u76ee\u5417\uff1f\u8fd9\u4f1a\u5220\u9664\u9879\u76ee\u7684\u6240\u6709\u6587\u4ef6\u4e0e\u6570\u636e\uff0c\u4e14\u4e0d\u53ef\u6062\u590d\u3002",
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
      done: "Done",
      pipelineHint: "Run steps in order 1\u21922\u21923\u21924. Completed steps are disabled to prevent re-runs.",
      deleteProject: "Delete project",
      deleteConfirm: "Delete this project? This will remove all project files and cannot be undone.",
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

  const isBusy = loadingProject || busyAction !== null;

  const ingestDone = Boolean(selectedProject?.paper_hash);
  const indexDone = Boolean(selectedProject?.repo_hash);
  const alignDone = Boolean(selectedProject?.alignment_path);
  const vectorsDone = Boolean(
    selectedProject?.paper_vector_path &&
      selectedProject?.code_vector_path &&
      selectedProject?.paper_bm25_path &&
      selectedProject?.code_bm25_path,
  );

  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const createNameRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!selectedId) return;
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [selectedId, qaLog.length]);

  useEffect(() => {
    if (!createOpen) return;
    window.setTimeout(() => {
      createNameRef.current?.focus();
    }, 0);
  }, [createOpen, createStep]);

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
    setLoadingProject(true);
    Promise.all([getProject(selectedId), getSummary(selectedId), getQaLog(selectedId)])
      .then(([project, summaryResp, qaResp]) => {
        setSelectedProject(project);
        setSummary({ text: summaryResp.summary || "" });
        setQaLog(qaResp.entries || []);
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => setLoadingProject(false));
  }, [selectedId]);

  function openCreate() {
    setError(null);
    setCreateStep(1);
    setCreateOpen(true);
  }

  function closeCreate() {
    setCreateOpen(false);
    setCreateStep(1);
  }

  async function submitCreate() {
    setError(null);
    setBusyAction("create");
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
      closeCreate();
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (createStep === 1) {
      setCreateStep(2);
      return;
    }
    await submitCreate();
  }

  async function handleDeleteSelected() {
    if (!selectedId) return;
    if (!window.confirm(t.deleteConfirm)) return;
    setError(null);
    setBusyAction("delete");
    try {
      await deleteProject(selectedId);
      setSelectedId(null);
      setSelectedProject(null);
      setSummary({ text: "" });
      setQaLog([]);
      await refreshProjects();
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleIngest() {
    if (!selectedId) return;
    setError(null);
    setBusyAction("ingest");
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
      setBusyAction(null);
    }
  }

  async function handleIndexCode() {
    if (!selectedId) return;
    setError(null);
    setBusyAction("index");
    try {
      await indexCode(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId || !question.trim()) return;
    setError(null);
    setBusyAction("ask");
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
      setBusyAction(null);
    }
  }

  async function handleAlign() {
    if (!selectedId) return;
    setError(null);
    setBusyAction("align");
    try {
      await alignProject(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleBuildVectors() {
    if (!selectedId) return;
    setError(null);
    setBusyAction("vectors");
    try {
      await buildVectors(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  const pipelineProgress = useMemo(() => {
    const steps = [ingestDone, indexDone, alignDone, vectorsDone];
    return steps.filter(Boolean).length;
  }, [alignDone, indexDone, ingestDone, vectorsDone]);

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

      <div className="layout-two">
        <aside className="sidebar-shell">
          <div className="sidebar-actions">
            <button className="primary" onClick={openCreate} disabled={isBusy}>
              {t.createBtn}
            </button>
          </div>

          <section className="card">
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
          </section>

          <section className="card">
            <div className="card-header">
              <h2>{t.detail}</h2>
              <button
                className="danger"
                onClick={handleDeleteSelected}
                disabled={!selectedId || isBusy}
              >
                {busyAction === "delete" ? t.working : t.deleteProject}
              </button>
            </div>
            <div className="button-row" style={{ marginTop: 8, flexWrap: "wrap" }}>
              <button
                className="ghost"
                onClick={handleIngest}
                disabled={!selectedId || isBusy || ingestDone}
              >
                {busyAction === "ingest" ? t.working : `1. ${t.ingest}${ingestDone ? ` (${t.done})` : ""}`}
              </button>
              <button
                className="ghost"
                onClick={handleIndexCode}
                disabled={!selectedId || isBusy || !ingestDone || indexDone}
              >
                {busyAction === "index" ? t.working : `2. ${t.indexCode}${indexDone ? ` (${t.done})` : ""}`}
              </button>
              <button
                className="ghost"
                onClick={handleAlign}
                disabled={!selectedId || isBusy || !ingestDone || !indexDone || alignDone}
              >
                {busyAction === "align" ? t.working : `3. ${t.align}${alignDone ? ` (${t.done})` : ""}`}
              </button>
              <button
                className="ghost"
                onClick={handleBuildVectors}
                disabled={!selectedId || isBusy || !ingestDone || !indexDone || vectorsDone}
              >
                {busyAction === "vectors"
                  ? t.working
                  : `4. ${t.buildVectors}${vectorsDone ? ` (${t.done})` : ""}`}
              </button>
            </div>
            <p className="pipeline-hint">{t.pipelineHint}</p>

            {selectedProject ? (
              <div className="detail-grid">
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
                <div>
                  <p className="label">{t.buildVectors}</p>
                  <p>{vectorsDone ? t.done : "-"}</p>
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
        </aside>

        <main className="chat-shell">
          <div className="chat-header">
            <div>
              <p className="eyebrow">{t.ask}</p>
              <h2 className="chat-title">{selectedProject ? selectedProject.name : t.selectProject}</h2>
            </div>
            <div className="chat-meta">
              <span>
                {qaLog.length} msgs | {pipelineProgress}/4
              </span>
            </div>
          </div>

          <div className="chat-body">
            {!selectedId ? (
              <div className="empty-callout">
                <p className="empty">{t.selectProject}</p>
                <button className="primary" onClick={openCreate} disabled={isBusy}>
                  {t.createBtn}
                </button>
              </div>
            ) : qaLog.length === 0 ? (
              <p className="empty">{t.noQuestions}</p>
            ) : (
              qaLog.map((entry, index) => (
                <div className="chat-turn" key={`${entry.created_at}-${index}`}>
                  <div className="msg msg-user">{entry.question}</div>
                  <div className="msg msg-assistant">
                    <div>{entry.answer}</div>
                    {entry.evidence && entry.evidence.length > 0 && (
                      <div className="msg-evidence">
                        {entry.evidence.slice(0, 2).map((ev, evIndex) => (
                          <div className="evidence-line" key={`${ev.path}-${evIndex}`}>
                            <span className="mono">{ev.path || "unknown"}</span>
                            {ev.name ? ` :: ${ev.name}` : ""}
                            {ev.line ? ` (L${ev.line})` : ""}
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="msg-meta">{new Date(entry.created_at).toLocaleString()}</div>
                  </div>
                </div>
              ))
            )}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-compose" onSubmit={handleAsk}>
            <div className="compose-row">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What positional encoding is used and why?"
                disabled={!selectedId || isBusy}
              />
              <button type="submit" className="primary" disabled={!selectedId || isBusy}>
                {busyAction === "ask" ? t.working : t.submit}
              </button>
            </div>
          </form>

          {error && <div className="error chat-error">{error}</div>}
        </main>
      </div>

      {createOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) closeCreate();
          }}
        >
          <div className="modal" role="dialog" aria-modal="true" aria-label={t.create}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">{t.create}</p>
                <h2 style={{ margin: 0 }}>{t.create}</h2>
              </div>
              <button className="modal-close" onClick={closeCreate} aria-label="Close">
                X
              </button>
            </div>

            <div className="stepper" aria-label="Create project steps">
              <div className={createStep === 1 ? "step active" : "step"}>
                <span className="step-dot">1</span>
                <span className="step-label">{t.projectName}</span>
              </div>
              <div className={createStep === 2 ? "step active" : "step"}>
                <span className="step-dot">2</span>
                <span className="step-label">{t.focusPoints}</span>
              </div>
            </div>

            <form className="modal-body form" onSubmit={handleCreate}>
              {createStep === 1 ? (
                <>
                  <label>
                    {t.projectName}
                    <input
                      ref={createNameRef}
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
                </>
              ) : (
                <>
                  <label>
                    {t.focusPoints}
                    <input
                      value={form.focus_points}
                      onChange={(e) => setForm({ ...form, focus_points: e.target.value })}
                      placeholder="positional encoding, loss, sampler"
                    />
                  </label>
                  <p className="empty" style={{ margin: 0 }}>
                    {lang === "zh"
                      ? "可选：填写关注点，帮助问答更聚焦。"
                      : "Optional: add a few focus points to steer Q&A."}
                  </p>
                </>
              )}

              {error && <div className="error">{error}</div>}

              <div className="modal-footer">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => (createStep === 1 ? closeCreate() : setCreateStep(1))}
                  disabled={isBusy}
                >
                  {createStep === 1
                    ? (lang === "zh" ? "取消" : "Cancel")
                    : (lang === "zh" ? "上一步" : "Back")}
                </button>
                {createStep === 1 ? (
                  <button
                    type="button"
                    className="primary"
                    onClick={() => setCreateStep(2)}
                    disabled={isBusy || !form.name.trim() || !form.paper_url.trim() || !form.repo_url.trim()}
                  >
                    {lang === "zh" ? "下一步" : "Next"}
                  </button>
                ) : (
                  <button type="submit" className="primary" disabled={isBusy}>
                    {busyAction === "create" ? t.working : t.createBtn}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
