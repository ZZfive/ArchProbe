import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  askProjectStream,
  abortAskProjectStream,
  abortOverviewStream,
  alignProject,
  buildVectors,
  createProject,
  deleteProject,
  generateOverviewFull,
  generateOverviewQuick,
  getCodeFile,
  getCodeSnippet,
  getOverview,
  getProject,
  getQaLog,
  indexCode,
  ingestProject,
  listProjects,
  Project,
} from "./api";

export default function App() {
  type CodeRef = {
    path: string;
    line: number;
    name: string;
    start_line: number;
    end_line: number;
  };

  const [lang, setLang] = useState<"zh" | "en">("zh");
  const [guideOpen, setGuideOpen] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createStep, setCreateStep] = useState<1 | 2>(1);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [qaLog, setQaLog] = useState<
    Array<{
      question: string;
      answer: string;
      created_at: string;
      code_refs?: CodeRef[];
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
  const [createError, setCreateError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  type CodeSnippetState = {
    content: string;
    language: string;
    loading: boolean;
    error?: string;
  };

  const [codeSnippets, setCodeSnippets] = useState<Record<string, CodeSnippetState>>({});
  const [selectedCodeFile, setSelectedCodeFile] = useState<{ path: string; content: string } | null>(null);
  const [showCodeViewer, setShowCodeViewer] = useState(false);
  const [codeViewerHighlight, setCodeViewerHighlight] = useState<{ startLine: number; endLine: number } | null>(null);

  const [activeTab, setActiveTab] = useState<"chat" | "overview">("chat");
  const [overview, setOverview] = useState<string | null>(null);
  const [overviewVersion, setOverviewVersion] = useState<string | null>(null);
  const [isGeneratingOverview, setIsGeneratingOverview] = useState(false);
  const [streamingOverview, setStreamingOverview] = useState<string | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);

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
      ask: "\u8be2\u95ee",
      question: "\u95ee\u9898",
      submit: "\u53d1\u9001",
      emptyProjects: "\u6682\u65e0\u9879\u76ee",
      selectProject: "\u8bf7\u9009\u62e9\u9879\u76ee\u67e5\u770b\u8be6\u60c5\u3002",
      noQuestions: "\u6682\u65e0\u95ee\u7b54\u3002",
      chat: "\u5bf9\u8bdd",
      overview: "\u9879\u76ee\u6982\u89c8",
      overviewQuick: "\u751f\u6210\u5feb\u901f\u6982\u89c8",
      overviewFull: "\u751f\u6210\u5b8c\u6574\u6982\u89c8",
      overviewQuickDesc: "\u57fa\u4e8e README \u548c\u8bba\u6587\u6458\u8981\u5feb\u901f\u751f\u6210",
      overviewFullDesc: "\u57fa\u4e8e\u5b8c\u6574\u8bba\u6587\u548c\u4ee3\u7801\u7ed3\u6784\u8be6\u7ec6\u751f\u6210",
      working: "\u5904\u7406\u4e2d...",
      done: "\u5df2\u5b8c\u6210",
      pipelineHint:
        "\u8bf7\u6309 1\u21922\u21923\u21924 \u7684\u987a\u5e8f\u6267\u884c\uff0c\u6bcf\u4e00\u6b65\u90fd\u9700\u8981\u524d\u4e00\u6b65\u5b8c\u6210\u540e\u624d\u80fd\u8fdb\u884c\u3002",
      deleteProject: "\u5220\u9664\u9879\u76ee",
      deleteConfirm:
        "\u786e\u5b9a\u5220\u9664\u8be5\u9879\u76ee\u5417\uff1f\u8fd9\u4f1a\u5220\u9664\u9879\u76ee\u7684\u6240\u6709\u6587\u4ef6\u4e0e\u6570\u636e\uff0c\u4e14\u4e0d\u53ef\u6062\u590d\u3002",
      guideTitle: "\u4f7f\u7528\u6307\u5357",
      guideToggle: "\u70b9\u51fb\u67e5\u770b\u6216\u6536\u8d77",
      guideHint: "\u6309 1\u21922\u21923\u21924 \u987a\u5e8f\u6267\u884c\uff0c\u524d\u4e00\u6b65\u5b8c\u6210\u540e\u624d\u80fd\u7ee7\u7eed\u3002",
      guideSteps: [
        "\u6b65\u9aa4 1\uff1a\u89e3\u6790\u8bba\u6587\uff08\u524d\u63d0\uff1a\u5df2\u521b\u5efa\u9879\u76ee\uff09\u2192 \u751f\u6210\u6bb5\u843d\u7ed3\u6784",
        "\u6b65\u9aa4 2\uff1a\u7d22\u5f15\u4ee3\u7801\uff08\u524d\u63d0\uff1a\u5df2\u89e3\u6790\u8bba\u6587\uff09\u2192 \u751f\u6210\u6587\u4ef6\u7d22\u5f15",
        "\u6b65\u9aa4 3\uff1a\u5bf9\u7167\uff08\u524d\u63d0\uff1a\u5df2\u7d22\u5f15\u4ee3\u7801\uff09\u2192 \u5173\u8054\u6bb5\u843d\u4e0e\u4ee3\u7801",
        "\u6b65\u9aa4 4\uff1a\u6784\u5efa\u5411\u91cf\uff08\u524d\u63d0\uff1a\u5df2\u5bf9\u7167\uff09\u2192 \u7528\u4e8e\u68c0\u7d22\u95ee\u7b54",
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
      ask: "Ask a Question",
      question: "Question",
      submit: "Send",
      emptyProjects: "No projects yet.",
      selectProject: "Select a project to view details.",
      noQuestions: "No questions yet.",
      chat: "Chat",
      overview: "Project overview",
      overviewQuick: "Generate quick overview",
      overviewFull: "Generate full overview",
      overviewQuickDesc: "Quick generation from README and paper abstract",
      overviewFullDesc: "Detailed generation from full paper and code structure",
      working: "Working...",
      done: "Done",
      pipelineHint: "Run steps in order 1\u21922\u21923\u21924. Each step requires the previous one to be completed first.",
      deleteProject: "Delete project",
      deleteConfirm: "Delete this project? This will remove all project files and cannot be undone.",
      guideTitle: "Usage Guide",
      guideToggle: "Click to expand or collapse",
      guideHint: "Run steps 1\u21922\u21923\u21924 in order. Complete previous step before proceeding.",
      guideSteps: [
        "Step 1: Ingest paper (prereq: project created) \u2192 parse paragraphs",
        "Step 2: Index code (prereq: paper ingested) \u2192 build file index",
        "Step 3: Align (prereq: code indexed) \u2192 link paragraphs with code",
        "Step 4: Build vectors (prereq: aligned) \u2192 enable Q&A retrieval",
      ],
    },
  } as const;

  const t = copy[lang];

  const isBusyGlobal = loadingProject || busyAction !== null;
  const isBusyPipeline = busyAction === "delete" || busyAction === "ingest" || busyAction === "index" || busyAction === "align" || busyAction === "vectors";
  const isBusyChat = busyAction === "ask";
  const isBusyCreate = busyAction === "create";

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
  const selectedIdRef = useRef<string | null>(null);
  const codeViewerBodyRef = useRef<HTMLDivElement | null>(null);
  const askRunIdRef = useRef(0);
  const overviewRunIdRef = useRef(0);

  function isAbortError(err: unknown): boolean {
    return (
      (err instanceof DOMException && err.name === "AbortError") ||
      (err instanceof Error && err.name === "AbortError")
    );
  }

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    return () => {
      abortAskProjectStream();
      abortOverviewStream();
    };
  }, []);

  useEffect(() => {
    if (!showCodeViewer) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        closeCodeViewer();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showCodeViewer]);

  useEffect(() => {
    if (!showCodeViewer) return;
    if (!selectedCodeFile) return;
    if (!codeViewerHighlight) return;

    window.setTimeout(() => {
      const el = codeViewerBodyRef.current?.querySelector(
        `[data-line='${codeViewerHighlight.startLine}']`
      ) as HTMLElement | null;
      el?.scrollIntoView({ block: "center" });
    }, 0);
  }, [codeViewerHighlight, selectedCodeFile, showCodeViewer]);

  useEffect(() => {
    if (!selectedId) return;
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [selectedId, qaLog.length, streamingAnswer, isStreaming]);

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

  function codeSnippetKey(projectId: string, ref: CodeRef): string {
    return `${projectId}::${ref.path}::${ref.start_line}-${ref.end_line}`;
  }

  function getErrorMessage(err: unknown, fallback: string): string {
    return err instanceof Error ? err.message : fallback;
  }

  async function fetchCodeSnippetForRef(
    projectId: string,
    ref: CodeRef,
    opts?: { force?: boolean }
  ): Promise<void> {
    const force = Boolean(opts?.force);
    const key = codeSnippetKey(projectId, ref);

    let started = false;
    setCodeSnippets((prev) => {
      const existing = prev[key];
      if (existing?.loading) return prev;
      if (!force && existing && (existing.content || existing.error)) {
        return prev;
      }
      started = true;
      return {
        ...prev,
        [key]: {
          content: "",
          language: "",
          loading: true,
        },
      };
    });

    if (!started) return;

    try {
      const resp = await getCodeSnippet(projectId, ref.path, ref.start_line, ref.end_line);
      setCodeSnippets((prev) => ({
        ...prev,
        [key]: {
          content: resp.content,
          language: resp.language,
          loading: false,
        },
      }));
    } catch (err) {
      setCodeSnippets((prev) => ({
        ...prev,
        [key]: {
          content: "",
          language: "text",
          loading: false,
          error: getErrorMessage(err, "Failed to load code snippet"),
        },
      }));
    }
  }

  async function ensureCodeSnippetsForRefs(projectId: string, refs: CodeRef[]): Promise<void> {
    const uniqueKeys = new Set<string>();
    const uniqueRefs: CodeRef[] = [];
    for (const ref of refs) {
      const key = codeSnippetKey(projectId, ref);
      if (uniqueKeys.has(key)) continue;
      uniqueKeys.add(key);
      uniqueRefs.push(ref);
    }

    await Promise.all(uniqueRefs.map((ref) => fetchCodeSnippetForRef(projectId, ref)));
  }

  async function openCodeViewerForRef(projectId: string, ref: CodeRef): Promise<void> {
    setShowCodeViewer(true);
    setSelectedCodeFile(null);
    setCodeViewerHighlight({ startLine: ref.start_line, endLine: ref.end_line });

    try {
      const resp = await getCodeFile(projectId, ref.path);
      if (selectedIdRef.current !== projectId) return;
      setSelectedCodeFile({ path: resp.path, content: resp.content });
    } catch (err) {
      if (selectedIdRef.current !== projectId) return;
      const message = err instanceof Error ? err.message : "Failed to load code file";
      setSelectedCodeFile({ path: ref.path, content: `// ${message}` });
    }
  }

  function closeCodeViewer() {
    setShowCodeViewer(false);
    setSelectedCodeFile(null);
    setCodeViewerHighlight(null);
  }

  async function refreshProjects() {
    const data = await listProjects();
    setProjects(data);
    if (!selectedId && data.length > 0) {
      setSelectedId(data[0].id);
    }
  }

  useEffect(() => {
    refreshProjects().catch((err) => setPipelineError(err.message));
  }, []);

  useEffect(() => {
    askRunIdRef.current += 1;
    overviewRunIdRef.current += 1;
    abortAskProjectStream();
    abortOverviewStream();

    setBusyAction((prev) => (prev === "ask" ? null : prev));

    setIsStreaming(false);
    setStreamingAnswer(null);
    setCodeSnippets({});
    setShowCodeViewer(false);
    setSelectedCodeFile(null);
    setCodeViewerHighlight(null);
    if (!selectedId) {
      setSelectedProject(null);
      setQaLog([]);
      return;
    }
    setLoadingProject(true);
    Promise.all([getProject(selectedId), getQaLog(selectedId)])
      .then(([project, qaResp]) => {
        setSelectedProject(project);
        setQaLog(qaResp.entries || []);
      })
      .catch((err) => {
        setPipelineError(err.message);
      })
      .finally(() => setLoadingProject(false));
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const refs = qaLog.flatMap((entry) => entry.code_refs || []);
    if (refs.length === 0) return;
    void ensureCodeSnippetsForRefs(selectedId, refs);
  }, [qaLog, selectedId]);

  useEffect(() => {
    setOverview(null);
    setOverviewVersion(null);
    setStreamingOverview(null);
    setIsGeneratingOverview(false);
    setOverviewError(null);

    if (!selectedId) return;

    let cancelled = false;
    getOverview(selectedId)
      .then((resp) => {
        if (cancelled) return;
        setOverview(resp.content);
        setOverviewVersion(resp.version);
      })
      .catch(() => {
        if (cancelled) return;
        setOverview(null);
        setOverviewVersion(null);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  function openCreate() {
    setCreateError(null);
    setCreateStep(1);
    setCreateOpen(true);
  }

  function closeCreate() {
    setCreateOpen(false);
    setCreateStep(1);
  }

  async function submitCreate() {
    setCreateError(null);
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
        setCreateError(err.message);
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

  async function handleDeleteProject(projectId: string) {
    if (!window.confirm(t.deleteConfirm)) return;
    setPipelineError(null);
    setBusyAction("delete");
    try {
      await deleteProject(projectId);

      if (selectedIdRef.current === projectId) {
        setSelectedId(null);
        setSelectedProject(null);
        setQaLog([]);
        setOverview(null);
        setOverviewVersion(null);
        setStreamingOverview(null);
        setIsGeneratingOverview(false);
        setOverviewError(null);
      }

      await refreshProjects();
    } catch (err) {
      if (err instanceof Error) {
        setPipelineError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleIngest() {
    if (!selectedId) return;
    setPipelineError(null);
    setBusyAction("ingest");
    try {
      await ingestProject(selectedId);
      const project = await getProject(selectedId);
      const qaResp = await getQaLog(selectedId);
      setSelectedProject(project);
      setQaLog(qaResp.entries || []);
    } catch (err) {
      if (err instanceof Error) {
        setPipelineError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleIndexCode() {
    if (!selectedId) return;
    setPipelineError(null);
    setBusyAction("index");
    try {
      await indexCode(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setPipelineError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;

    const submittedQuestion = question.trim();
    if (!submittedQuestion) return;

    abortAskProjectStream();
    askRunIdRef.current += 1;
    const runId = askRunIdRef.current;
    const projectId = selectedId;

    setChatError(null);
    setBusyAction("ask");
    setIsStreaming(true);
    setStreamingAnswer("");

    let finalAnswer = "";
    let finalCodeRefs: CodeRef[] = [];

    try {
      await askProjectStream(
        projectId,
        submittedQuestion,
        (chunk) => {
          if (selectedIdRef.current !== projectId) return;
          if (askRunIdRef.current !== runId) return;
          finalAnswer += chunk;
          setStreamingAnswer((prev) => (prev ?? "") + chunk);
        },
        (result) => {
          if (selectedIdRef.current !== projectId) return;
          if (askRunIdRef.current !== runId) return;
          finalAnswer = result.answer;
          finalCodeRefs = result.code_refs || [];
        },
        (error) => {
          throw new Error(error);
        }
      );

      if (selectedIdRef.current !== projectId) return;
      if (askRunIdRef.current !== runId) return;

      setQaLog((prev) => [
        ...prev,
        {
          question: submittedQuestion,
          answer: finalAnswer,
          created_at: new Date().toISOString(),
          code_refs: finalCodeRefs,
          evidence: [],
        },
      ]);

      if (finalCodeRefs.length > 0) {
        void ensureCodeSnippetsForRefs(projectId, finalCodeRefs);
      }

      setQuestion("");
    } catch (err) {
      if (isAbortError(err)) return;
      if (err instanceof Error) {
        setChatError(err.message);
      }
    } finally {
      if (askRunIdRef.current !== runId) return;
      setIsStreaming(false);
      setStreamingAnswer(null);
      setBusyAction(null);
    }
  }

  async function generateOverview(mode: "quick" | "full") {
    if (!selectedId) return;

    const projectId = selectedId;
    const runLang = lang;

    abortOverviewStream();
    overviewRunIdRef.current += 1;
    const runId = overviewRunIdRef.current;

    setOverviewError(null);
    setIsGeneratingOverview(true);
    setStreamingOverview("");

    let fullContent = "";

    try {
      const fn = mode === "quick" ? generateOverviewQuick : generateOverviewFull;
      await fn(
        projectId,
        runLang,
        (chunk) => {
          if (selectedIdRef.current !== projectId) return;
          if (overviewRunIdRef.current !== runId) return;
          fullContent += chunk;
          setStreamingOverview((prev) => (prev ?? "") + chunk);
        },
        (version) => {
          if (selectedIdRef.current !== projectId) return;
          if (overviewRunIdRef.current !== runId) return;
          setOverview(fullContent);
          setOverviewVersion(version);
        },
        (error) => {
          throw new Error(error);
        }
      );

      if (selectedIdRef.current !== projectId) return;
      if (overviewRunIdRef.current !== runId) return;

      try {
        const resp = await getOverview(projectId);
        if (selectedIdRef.current !== projectId) return;
        setOverview(resp.content);
        setOverviewVersion(resp.version);
      } catch {
        // Best-effort refresh; keep streamed content.
      }
    } catch (err) {
      if (selectedIdRef.current !== projectId) return;
      if (overviewRunIdRef.current !== runId) return;
      if (isAbortError(err)) return;
      if (err instanceof Error) {
        setOverviewError(err.message);
      }
    } finally {
      if (selectedIdRef.current !== projectId) return;
      if (overviewRunIdRef.current !== runId) return;
      setIsGeneratingOverview(false);
      setStreamingOverview(null);
    }
  }

  async function handleAlign() {
    if (!selectedId) return;
    setPipelineError(null);
    setBusyAction("align");
    try {
      await alignProject(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setPipelineError(err.message);
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleBuildVectors() {
    if (!selectedId) return;
    setPipelineError(null);
    setBusyAction("vectors");
    try {
      await buildVectors(selectedId);
      const project = await getProject(selectedId);
      setSelectedProject(project);
    } catch (err) {
      if (err instanceof Error) {
        setPipelineError(err.message);
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
            <button className="primary" onClick={openCreate} disabled={isBusyGlobal}>
              {t.createBtn}
            </button>
          </div>

          <section className="card">
            <div className="card-header">
              <h2>{t.guideTitle}</h2>
              <button className="ghost" onClick={() => setGuideOpen(!guideOpen)}>
                {t.guideToggle}
              </button>
            </div>
            {!guideOpen && <p className="hint">{t.guideHint}</p>}
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
              <h2>{t.projects}</h2>
              <button className="ghost" onClick={() => setProjectsOpen(!projectsOpen)}>
                {projectsOpen ? (lang === "zh" ? "收起" : "Collapse") : (lang === "zh" ? "展开" : "Expand")}
              </button>
            </div>
            {!projectsOpen && (
              <p className="hint">
                {projects.length > 0
                  ? `${projects.length} ${lang === "zh" ? "个项目" : "projects"}${
                      selectedId
                        ? ` | ${lang === "zh" ? "当前" : "Current"}: ${
                            projects.find((p) => p.id === selectedId)?.name || ""
                          }`
                        : ""
                    }`
                  : t.emptyProjects}
              </p>
            )}
            {projectsOpen && (
              <div className="project-list">
                {projects.map((project) => {
                  const isActive = project.id === selectedId;
                  return (
                    <div
                      key={project.id}
                      className={isActive ? "project active" : "project"}
                      role="button"
                      tabIndex={0}
                      aria-current={isActive ? "true" : undefined}
                      onClick={() => setSelectedId(project.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedId(project.id);
                        }
                      }}
                    >
                      <div className="project-name">{project.name}</div>
                      <div className="project-meta">{project.paper_url}</div>
                      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                        <button
                          type="button"
                          className="danger"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteProject(project.id);
                          }}
                          disabled={isBusyPipeline}
                        >
                          {busyAction === "delete" ? t.working : t.deleteProject}
                        </button>
                      </div>
                    </div>
                  );
                })}
                {projects.length === 0 && <div className="empty">{t.emptyProjects}</div>}
              </div>
            )}
          </section>

          {selectedId && (
            <section className="card">
              <div className="card-header">
                <h2>{t.detail}</h2>
                <button className="ghost" onClick={() => setDetailOpen(!detailOpen)} disabled={!selectedProject}>
                  {detailOpen
                    ? (lang === "zh" ? "隐藏详情" : "Hide details")
                    : (lang === "zh" ? "显示详情" : "Show details")}
                </button>
              </div>
              <div className="button-grid">
                <button
                  className="ghost"
                  onClick={handleIngest}
                  disabled={isBusyPipeline || ingestDone}
                >
                  {busyAction === "ingest" ? t.working : `1. ${t.ingest}${ingestDone ? ` (${t.done})` : ""}`}
                </button>
                <button
                  className="ghost"
                  onClick={handleIndexCode}
                  disabled={isBusyPipeline || !ingestDone || indexDone}
                >
                  {busyAction === "index" ? t.working : `2. ${t.indexCode}${indexDone ? ` (${t.done})` : ""}`}
                </button>
                <button
                  className="ghost"
                  onClick={handleAlign}
                  disabled={isBusyPipeline || !ingestDone || !indexDone || alignDone}
                >
                  {busyAction === "align" ? t.working : `3. ${t.align}${alignDone ? ` (${t.done})` : ""}`}
                </button>
                <button
                  className="ghost"
                  onClick={handleBuildVectors}
                  disabled={isBusyPipeline || !ingestDone || !indexDone || vectorsDone}
                >
                  {busyAction === "vectors"
                    ? t.working
                    : `4. ${t.buildVectors}${vectorsDone ? ` (${t.done})` : ""}`}
                </button>
              </div>
              <p className="pipeline-hint">{t.pipelineHint}</p>
              {pipelineError && <div className="error" style={{ marginTop: 10 }}>{pipelineError}</div>}
              {detailOpen && selectedProject && (
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
              )}
            </section>
          )}

          <section className="card">
            <h2>{lang === "zh" ? "导出" : "Export"}</h2>
            <div className="export-actions">
              <button
                className="ghost"
                onClick={() => {
                  if (!selectedProject) return;
                  const content = [`# ${selectedProject.name}`,
                    ``,
                    `**${lang === "zh" ? "论文" : "Paper"}**: ${selectedProject.paper_url}`,
                    `**${lang === "zh" ? "仓库" : "Repository"}**: ${selectedProject.repo_url}`,
                    selectedProject.focus_points?.length ? `**${lang === "zh" ? "关注点" : "Focus"}**: ${selectedProject.focus_points.join(", ")}` : "",
                    ``,
                    `## ${lang === "zh" ? "对话记录" : "Conversation"}`,
                    ...(qaLog.length ? qaLog.flatMap((entry, i) => [``, `### Q${i + 1}: ${entry.question}`, ``, entry.answer, ``, `*${new Date(entry.created_at).toLocaleString()}*`]) : [`${lang === "zh" ? "暂无问答记录" : "No Q&A records yet"}`]),
                    ``,
                    `## ${lang === "zh" ? "草稿" : "Draft"}`,
                    question.trim() || (lang === "zh" ? "（无）" : "(none)"),
                  ].filter(Boolean).join("\n");
                  const blob = new Blob([content], { type: "text/markdown" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `${selectedProject.name}-${new Date().toISOString().slice(0, 16).replace(/[T:]/g, "-")}.md`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
                disabled={!selectedId}
              >
                {lang === "zh" ? "导出 Markdown" : "Export Markdown"}
              </button>
            </div>
          </section>
        </aside>

        <main className="chat-shell">
          <div className="chat-header">
            <div>
              <p className="eyebrow">{activeTab === "chat" ? t.chat : t.overview}</p>
              <h2 className="chat-title">{selectedProject ? selectedProject.name : t.selectProject}</h2>
            </div>
            <div className="chat-meta">
              {activeTab === "chat" ? (
                <span>
                  {qaLog.length} msgs | {pipelineProgress}/4
                </span>
              ) : (
                <span>
                  {overviewVersion
                    ? `v${overviewVersion}`
                    : overview
                      ? (lang === "zh" ? "已生成" : "Generated")
                      : (lang === "zh" ? "未生成" : "Not generated")}
                  {" "}| {pipelineProgress}/4
                </span>
              )}
            </div>
          </div>

          <div
            style={{
              display: "flex",
              gap: 10,
              padding: "10px 20px",
              borderBottom: "1px solid rgba(210, 214, 230, 0.7)",
              background: "rgba(255, 255, 255, 0.35)",
            }}
          >
            <button
              type="button"
              className={activeTab === "chat" ? "primary" : "ghost"}
              onClick={() => setActiveTab("chat")}
            >
              对话/Chat
            </button>
            <button
              type="button"
              className={activeTab === "overview" ? "primary" : "ghost"}
              onClick={() => setActiveTab("overview")}
            >
              项目概览/Overview
            </button>
          </div>

          <div className="chat-body">
            {activeTab === "chat" ? (
              <>
                {!selectedId ? (
                  <div className="empty-callout">
                    <p className="empty">{t.selectProject}</p>
                    <button className="primary" onClick={openCreate} disabled={isBusyGlobal}>
                      {t.createBtn}
                    </button>
                  </div>
                ) : qaLog.length === 0 ? (
                  <p className="empty">{t.noQuestions}</p>
                ) : (
                  qaLog.map((entry, index) => (
                    <div className="chat-turn" key={`${entry.created_at}-${index}`}>
                      <div className="msg msg-user">{entry.question}</div>
                      <div className="msg msg-assistant markdown-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry.answer}</ReactMarkdown>
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
                        {(!entry.code_refs || entry.code_refs.length === 0) && (
                          <p className="hint related-code-empty-hint">
                            {lang === "zh"
                              ? "未返回相关代码引用。通常需要先完成：索引代码（步骤 2）和对照（步骤 3），完成后再提问更容易得到“相关代码”。"
                              : "No code references returned. Usually you need to run Code index (step 2) and Align (step 3), then ask again."}
                          </p>
                        )}
                        {entry.code_refs && entry.code_refs.length > 0 && (
                          <div className="related-code">
                            <div className="related-code-header">
                              <div className="related-code-title">相关代码 ({entry.code_refs.length})</div>
                            </div>
                            <div className="related-code-list">
                              {entry.code_refs.map((ref, refIndex) => {
                                const key = selectedId ? codeSnippetKey(selectedId, ref) : `${ref.path}::${ref.start_line}-${ref.end_line}`;
                                const snippet = selectedId ? codeSnippets[key] : undefined;
                                const snippetLines = snippet?.content ? snippet.content.split("\n") : [];

                                return (
                                  <div className="related-code-item" key={`${ref.path}-${ref.start_line}-${ref.end_line}-${refIndex}`}>
                                    <div className="related-code-meta">
                                      <div className="related-code-path mono">
                                        {ref.path} (L{ref.line}){ref.name ? ` :: ${ref.name}` : ""}
                                      </div>
                                      <button
                                        type="button"
                                        className="ghost related-code-open"
                                        onClick={() => {
                                          if (!selectedId) return;
                                          void openCodeViewerForRef(selectedId, ref);
                                        }}
                                        disabled={!selectedId}
                                      >
                                        查看完整文件
                                      </button>
                                    </div>

                                    <div className="code-snippet" data-language={snippet?.language || ""}>
                                      {!snippet || snippet.loading ? (
                                        <div className="code-snippet-loading">加载代码片段...</div>
                                      ) : snippet.error ? (
                                        <div className="code-snippet-error">
                                          <div className="code-snippet-error-message">{snippet.error}</div>
                                          <div className="code-snippet-actions">
                                            <button
                                              type="button"
                                              className="ghost code-snippet-retry"
                                              onClick={() => {
                                                if (!selectedId) return;
                                                void fetchCodeSnippetForRef(selectedId, ref, { force: true });
                                              }}
                                            >
                                              {lang === "zh" ? "重试" : "Retry"}
                                            </button>
                                          </div>
                                        </div>
                                      ) : snippet?.content ? (
                                        <div className="code-lines" role="presentation">
                                          {snippetLines.map((line, lineIndex) => (
                                            <div className="code-line" key={`${key}-${lineIndex}`}>
                                              <span className="code-lineno">{ref.start_line + lineIndex}</span>
                                              <span className="code-content">{line || " "}</span>
                                            </div>
                                          ))}
                                        </div>
                                      ) : (
                                        <div className="code-snippet-loading">(暂无代码片段)</div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                        <div className="msg-meta">{new Date(entry.created_at).toLocaleString()}</div>
                      </div>
                    </div>
                  ))
                )}
                {isStreaming && streamingAnswer !== null && (
                  <div className="chat-turn" key="__streaming__">
                    <div className="msg msg-user">{question.trim()}</div>
                    <div className="msg msg-assistant markdown-body">
                      <div className="msg-meta" style={{ marginTop: 0, marginBottom: 8 }}>
                        <span>●</span> {lang === "zh" ? "生成中..." : "typing..."}
                      </div>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingAnswer}</ReactMarkdown>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </>
            ) : (
              <>
                {!selectedId ? (
                  <div className="empty-callout">
                    <p className="empty">{t.selectProject}</p>
                    <button className="primary" onClick={openCreate} disabled={isBusyGlobal}>
                      {t.createBtn}
                    </button>
                  </div>
                ) : (
                  <div>
                    {streamingOverview !== null || overview ? (
                      <div>
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => generateOverview("quick")}
                            disabled={isGeneratingOverview || isBusyPipeline}
                          >
                            {isGeneratingOverview ? t.working : t.overviewQuick}
                          </button>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => generateOverview("full")}
                            disabled={isGeneratingOverview || isBusyPipeline}
                          >
                            {isGeneratingOverview ? t.working : t.overviewFull}
                          </button>
                        </div>

                        <div className="markdown-body">
                        {isGeneratingOverview && streamingOverview !== null && (
                          <div className="msg-meta" style={{ marginTop: 0, marginBottom: 8 }}>
                            <span>●</span> {lang === "zh" ? "生成中..." : "generating..."}
                          </div>
                        )}
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {streamingOverview ?? overview ?? ""}
                        </ReactMarkdown>
                        </div>
                      </div>
                    ) : (
                      <div className="empty-callout">
                        <p className="empty">{lang === "zh" ? "暂无项目概览。" : "No overview yet."}</p>
                        <div style={{ display: "grid", gap: 12, maxWidth: 520 }}>
                          <div>
                            <button
                              type="button"
                              className="ghost"
                              onClick={() => generateOverview("quick")}
                              disabled={isGeneratingOverview || isBusyPipeline}
                            >
                              {isGeneratingOverview ? t.working : t.overviewQuick}
                            </button>
                            <p className="hint" style={{ margin: "6px 0 0" }}>{t.overviewQuickDesc}</p>
                          </div>
                          <div>
                            <button
                              type="button"
                              className="ghost"
                              onClick={() => generateOverview("full")}
                              disabled={isGeneratingOverview || isBusyPipeline}
                            >
                              {isGeneratingOverview ? t.working : t.overviewFull}
                            </button>
                            <p className="hint" style={{ margin: "6px 0 0" }}>{t.overviewFullDesc}</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {activeTab === "chat" && (
            <>
              <form className="chat-compose" onSubmit={handleAsk}>
                <div className="compose-row">
                  <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="What positional encoding is used and why?"
                    disabled={!selectedId || isBusyChat}
                  />
                  <button type="submit" className="primary" disabled={!selectedId || isBusyChat}>
                    {busyAction === "ask" ? t.working : t.submit}
                  </button>
                </div>
              </form>

              {chatError && <div className="error chat-error">{chatError}</div>}
            </>
          )}

          {activeTab === "overview" && overviewError && (
            <div className="error chat-error">{overviewError}</div>
          )}
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

              {createError && <div className="error">{createError}</div>}

              <div className="modal-footer">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => (createStep === 1 ? closeCreate() : setCreateStep(1))}
                  disabled={isBusyCreate}
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
                    disabled={isBusyCreate || !form.name.trim() || !form.paper_url.trim() || !form.repo_url.trim()}
                  >
                    {lang === "zh" ? "下一步" : "Next"}
                  </button>
                ) : (
                  <button type="submit" className="primary" disabled={isBusyCreate}>
                    {busyAction === "create" ? t.working : t.createBtn}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {showCodeViewer && (
        <div
          className="modal-backdrop code-viewer-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) closeCodeViewer();
          }}
        >
          <div className="code-viewer" role="dialog" aria-modal="true" aria-label="Code viewer">
            <div className="code-viewer-header">
              <div>
                <p className="eyebrow">Code</p>
                <h2 style={{ margin: 0, fontSize: "1.1rem" }}>
                  {selectedCodeFile?.path || "Loading..."}
                </h2>
                {codeViewerHighlight && (
                  <p className="hint" style={{ margin: "6px 0 0" }}>
                    Highlight: L{codeViewerHighlight.startLine} - L{codeViewerHighlight.endLine}
                  </p>
                )}
              </div>
              <button className="modal-close" onClick={closeCodeViewer} aria-label="Close">
                X
              </button>
            </div>

            <div className="code-viewer-body" ref={codeViewerBodyRef}>
              {selectedCodeFile ? (
                <div className="code-file" role="presentation">
                  {selectedCodeFile.content.split("\n").map((line, idx) => {
                    const lineNo = idx + 1;
                    const isHighlighted =
                      Boolean(codeViewerHighlight) &&
                      lineNo >= (codeViewerHighlight?.startLine ?? 0) &&
                      lineNo <= (codeViewerHighlight?.endLine ?? 0);

                    return (
                      <div
                        key={`${selectedCodeFile.path}-${lineNo}`}
                        className={isHighlighted ? "code-line highlight" : "code-line"}
                        data-line={lineNo}
                      >
                        <span className="code-lineno">{lineNo}</span>
                        <span className="code-content">{line || " "}</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="code-file-loading">Loading file...</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
