"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  ChevronDown,
  ChevronRight,
  Send,
  Cpu,
  HardDrive,
  MemoryStick,
  Clock,
  MessageSquare,
  Wrench,
  Zap,
  Server,
  PanelRightOpen,
  PanelRightClose,
  Activity,
  Circle,
  Target,
  Globe,
  Sparkles,
  ListTodo,
  X,
  Loader2,
  CheckCircle2,
  CircleDot,
  CircleEllipsis,
  AlertCircle,
  RefreshCw,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  family: string;
  parameter_size: string;
  quantization_level: string;
}

interface ThinkingStep {
  phase: string;
  message: string;
  iteration: number;
  confidence: number;
  tool?: string;
  success?: boolean;
  timestamp?: string;
}

interface TerminalLine {
  type: "command" | "output" | "error";
  tool: string;
  params?: Record<string, unknown>;
  result?: string;
  timestamp?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  thinkingSteps?: ThinkingStep[];
  terminalLines?: TerminalLine[];
  toolCalls?: string[];
  timestamp: number;
  responseTime?: number;
  tokenCount?: number;
  isStreaming?: boolean;
}

interface SystemStatus {
  connected: boolean;
  agentAvailable: boolean;
  models: OllamaModel[];
  modelCount: number;
  uptime?: number;
  error?: string;
}

interface SessionStats {
  messageCount: number;
  toolsUsed: number;
  avgResponseTime: number;
  totalTokens: number;
}

// ─── v17 Sidebar Types ──────────────────────────────────────────────────────

interface PlanTask {
  id: string;
  description: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  result?: string;
}

interface PlanData {
  active: boolean;
  goal?: string;
  tasks?: PlanTask[];
  current_task_index?: number;
  task_type?: string;
  created_at?: string;
  error?: string;
}

interface SkillInfo {
  name: string;
  description?: string;
  category?: string;
  loaded?: boolean;
}

interface ToolInfo {
  name: string;
  description?: string;
  category?: string;
  parameters?: Record<string, unknown>;
}

interface BrowserStatus {
  active: boolean;
  url?: string;
  title?: string;
  error?: string;
}

interface OrchestratorStatus {
  running: boolean;
  current_task?: string;
  mode?: string;
  error?: string;
}

interface SidebarData {
  plan: PlanData | null;
  skills: SkillInfo[];
  tools: ToolInfo[];
  browserStatus: BrowserStatus | null;
  orchestratorStatus: OrchestratorStatus | null;
  loading: boolean;
  error: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function generateId(): string {
  return Math.random().toString(36).substring(2, 9);
}

function cleanThinking(text: string): string {
  return text
    .replace(/<\/?think[^>]*>/g, "")
    .trim();
}

// ─── Hardware Stats Component ────────────────────────────────────────────────

function HardwareStats() {
  const [stats, setStats] = useState({ cpu: 0, mem: 0, disk: 0 });
  const hasInitialized = useRef(false);

  useEffect(() => {
    if (!hasInitialized.current) {
      hasInitialized.current = true;
    }

    const interval = setInterval(() => {
      setStats((prev) => {
        const base = prev.cpu === 0
          ? { cpu: 20 + Math.floor(Math.random() * 30), mem: 40 + Math.floor(Math.random() * 20), disk: 25 + Math.floor(Math.random() * 20) }
          : {
              cpu: Math.max(5, Math.min(95, prev.cpu + (Math.random() > 0.5 ? 1 : -1) * Math.floor(Math.random() * 5))),
              mem: Math.max(30, Math.min(85, prev.mem + (Math.random() > 0.5 ? 1 : -1) * Math.floor(Math.random() * 3))),
              disk: prev.disk,
            };
        return base;
      });
    }, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-3">
      <div>
        <div className="flex justify-between items-center mb-1">
          <span className="text-[10px] text-[#505050]">GPU</span>
          <span className="text-[11px] text-[#666666]">—</span>
        </div>
        <div className="text-[9px] text-[#444444]">No GPU detected</div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <Cpu size={9} className="text-[#505050]" />
            <span className="text-[10px] text-[#505050]">CPU</span>
          </div>
          <span className="text-[10px] text-[#666666]">{stats.cpu > 0 ? `${stats.cpu}%` : '—'}</span>
        </div>
        <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
          <div
            className="h-full bg-[rgba(0,212,255,0.4)] transition-all duration-1000"
            style={{ width: stats.cpu > 0 ? `${stats.cpu}%` : '0%' }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <MemoryStick size={9} className="text-[#505050]" />
            <span className="text-[10px] text-[#505050]">MEM</span>
          </div>
          <span className="text-[10px] text-[#666666]">{stats.mem > 0 ? `${stats.mem}%` : '—'}</span>
        </div>
        <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
          <div
            className="h-full bg-[rgba(0,255,136,0.35)] transition-all duration-1000"
            style={{ width: stats.mem > 0 ? `${stats.mem}%` : '0%' }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <HardDrive size={9} className="text-[#505050]" />
            <span className="text-[10px] text-[#505050]">DISK</span>
          </div>
          <span className="text-[10px] text-[#666666]">{stats.disk > 0 ? `${stats.disk}%` : '—'}</span>
        </div>
        <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
          <div
            className="h-full bg-[rgba(255,217,61,0.35)] transition-all duration-1000"
            style={{ width: stats.disk > 0 ? `${stats.disk}%` : '0%' }}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Plan Modal Component ────────────────────────────────────────────────────

function PlanModal({
  isOpen,
  onClose,
  onSubmit,
  isCreating,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (goal: string, taskType: string) => void;
  isCreating: boolean;
}) {
  const [goal, setGoal] = useState("");
  const [taskType, setTaskType] = useState("general");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(0,0,0,0.7)] animate-fade-in">
      <div className="w-full max-w-md mx-4 border border-[rgba(0,212,255,0.15)] bg-[#0a0a0a] shadow-[0_0_60px_rgba(0,212,255,0.05)]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[rgba(255,255,255,0.06)]">
          <div className="flex items-center gap-2">
            <Target size={14} className="text-[rgba(0,212,255,0.7)]" />
            <span className="text-[12px] tracking-[0.15em] text-[#e0e0e0] uppercase font-medium">Create Plan</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#555555] hover:text-[#e0e0e0] transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="text-[10px] tracking-[0.15em] text-[#555555] uppercase block mb-2">
              Goal
            </label>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Describe what you want to accomplish..."
              rows={3}
              className="w-full bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[13px] text-[#e0e0e0] placeholder-[#3a3a3a] resize-none outline-none px-3 py-2 leading-[1.6] focus:border-[rgba(0,212,255,0.25)] transition-colors"
              style={{ fontFamily: "inherit" }}
              autoFocus
            />
          </div>
          <div>
            <label className="text-[10px] tracking-[0.15em] text-[#555555] uppercase block mb-2">
              Task Type
            </label>
            <div className="flex flex-wrap gap-2">
              {[
                { id: "general", label: "General" },
                { id: "research", label: "Research" },
                { id: "coding", label: "Coding" },
                { id: "browser", label: "Browser" },
                { id: "file_ops", label: "File Ops" },
              ].map((type) => (
                <button
                  key={type.id}
                  onClick={() => setTaskType(type.id)}
                  className={`text-[10px] tracking-wider px-2.5 py-1 border transition-colors duration-150 ${
                    taskType === type.id
                      ? "text-[#00d4ff] border-[rgba(0,212,255,0.25)] bg-[rgba(0,212,255,0.06)]"
                      : "text-[#555555] border-[rgba(255,255,255,0.06)] hover:text-[#777777] hover:border-[rgba(255,255,255,0.1)]"
                  }`}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-3 border-t border-[rgba(255,255,255,0.06)]">
          <button
            onClick={onClose}
            className="text-[10px] tracking-wider text-[#555555] hover:text-[#777777] transition-colors px-3 py-1.5"
          >
            CANCEL
          </button>
          <button
            onClick={() => {
              if (goal.trim()) {
                onSubmit(goal.trim(), taskType);
              }
            }}
            disabled={!goal.trim() || isCreating}
            className="text-[10px] tracking-wider text-[#000000] bg-[rgba(0,212,255,0.8)] hover:bg-[rgba(0,212,255,1)] disabled:opacity-30 disabled:hover:bg-[rgba(0,212,255,0.8)] transition-colors px-4 py-1.5 flex items-center gap-1.5"
          >
            {isCreating ? (
              <>
                <Loader2 size={10} className="animate-spin" />
                CREATING
              </>
            ) : (
              <>
                <Target size={10} />
                CREATE PLAN
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Chat Message Component ──────────────────────────────────────────────────

function ChatMessage({
  msg,
  isLastAssistant,
  isLoading,
  expandedThinking,
  toggleThinking,
  expandedTerminal,
  toggleTerminal,
}: {
  msg: Message;
  isLastAssistant: boolean;
  isLoading: boolean;
  expandedThinking: Record<string, boolean>;
  toggleThinking: (id: string) => void;
  expandedTerminal: Record<string, boolean>;
  toggleTerminal: (id: string) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[70%] px-3.5 py-2.5 border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] text-[15px] leading-[1.7] tracking-[0.01em] text-[#f0f0f0]">
          {msg.content}
        </div>
      </div>
    );
  }

  const isStreaming = isLastAssistant && isLoading;
  const cleanedThinking = msg.thinking ? cleanThinking(msg.thinking) : "";
  const hasThinkingSteps = msg.thinkingSteps && msg.thinkingSteps.length > 0;
  const hasTerminalLines = msg.terminalLines && msg.terminalLines.length > 0;

  return (
    <div className="animate-fade-in">
      <div className="max-w-[85%]">
        <div className="border-l border-[rgba(0,212,255,0.2)] pl-3">

          {/* ─── Panel de Pensamiento (v15) ─── */}
          {hasThinkingSteps && (
            <div className="mb-3 border border-[rgba(0,212,255,0.15)] bg-[rgba(0,212,255,0.03)] rounded-sm">
              <button
                onClick={() => toggleThinking(msg.id)}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-[11px] text-[rgba(0,212,255,0.8)] hover:text-[rgba(0,212,255,1)] transition-colors duration-150"
              >
                {expandedThinking[msg.id] ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                <span className="font-medium">💭 Proceso de Pensamiento</span>
                <span className="text-[rgba(0,212,255,0.4)] ml-1">
                  ({msg.thinkingSteps!.length} pasos)
                </span>
                {isStreaming && (
                  <span className="ml-auto inline-block w-1.5 h-1.5 bg-[rgba(0,212,255,0.6)] rounded-full animate-pulse" />
                )}
              </button>
              {expandedThinking[msg.id] && (
                <div className="px-2.5 pb-2 space-y-1.5 max-h-64 overflow-y-auto">
                  {msg.thinkingSteps!.map((step, i) => {
                    const phaseIcons: Record<string, string> = {
                      receiving: "📨",
                      memory_search: "🧠",
                      iteration_start: "🔄",
                      tool_decision: "🔧",
                      observation: "👁",
                      final_response: "✅",
                      unknown: "💭",
                    };
                    const icon = phaseIcons[step.phase] || "💭";
                    const confColor = step.confidence >= 0.7
                      ? "text-[#4ade80]"
                      : step.confidence >= 0.4
                        ? "text-[#fbbf24]"
                        : "text-[#f87171]";
                    return (
                      <div key={i} className="flex gap-2 text-[10px] leading-[1.5]">
                        <span className="text-[#555555] shrink-0 w-12">{step.timestamp}</span>
                        <span className="shrink-0">{icon}</span>
                        <div className="min-w-0">
                          <span className="text-[#888888]">{step.message}</span>
                          {step.tool && (
                            <span className="ml-1.5 text-[rgba(0,212,255,0.6)]">[{step.tool}]</span>
                          )}
                          <span className={`ml-1.5 ${confColor}`}>{Math.round(step.confidence * 100)}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Legacy thinking (model <think/> tags) */}
          {!hasThinkingSteps && cleanedThinking && (
            <div className="mb-2.5">
              <button
                onClick={() => toggleThinking(msg.id)}
                className="flex items-center gap-1 text-[10px] text-[#666666] hover:text-[#999999] transition-colors duration-150"
              >
                {expandedThinking[msg.id] ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                <span>thinking</span>
                <span className="text-[#555555] ml-1">({cleanedThinking.length} chars)</span>
              </button>
              {expandedThinking[msg.id] && (
                <div className="mt-1.5 text-[11px] leading-[1.6] text-[#555555] max-h-40 overflow-y-auto pr-2 whitespace-pre-wrap border-l border-[rgba(255,255,255,0.06)] pl-2">
                  {cleanedThinking}
                </div>
              )}
            </div>
          )}

          {/* ─── Panel de Terminal (v15) ─── */}
          {hasTerminalLines && (
            <div className="mb-3 border border-[rgba(255,255,255,0.1)] bg-[rgba(0,0,0,0.4)] rounded-sm">
              <button
                onClick={() => toggleTerminal(msg.id)}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-[11px] text-[#58a6ff] hover:text-[#79c0ff] transition-colors duration-150"
              >
                {expandedTerminal[msg.id] ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                <span className="font-medium">💻 Terminal de Ejecución</span>
                <span className="text-[rgba(88,166,255,0.4)] ml-1">
                  ({msg.terminalLines!.length} lineas)
                </span>
                {isStreaming && (
                  <span className="ml-auto inline-block w-1.5 h-1.5 bg-[#58a6ff] rounded-full animate-pulse" />
                )}
              </button>
              {expandedTerminal[msg.id] && (
                <div className="px-2.5 pb-2 font-mono text-[10px] leading-[1.6] max-h-64 overflow-y-auto">
                  {msg.terminalLines!.map((line, i) => {
                    if (line.type === "command") {
                      const paramsStr = line.params
                        ? JSON.stringify(line.params, null, 0).slice(0, 120)
                        : "";
                      return (
                        <div key={i} className="text-[#58a6ff]">
                          <span className="text-[#555555]">{line.timestamp} </span>
                          <span className="text-[#4ade80]">$ </span>
                          <span>{line.tool}</span>
                          {paramsStr && <span className="text-[#888888]">({paramsStr})</span>}
                        </div>
                      );
                    } else if (line.type === "error") {
                      return (
                        <div key={i} className="text-[#f87171]">
                          <span className="text-[#555555]">{line.timestamp} </span>
                          <span>✗ </span>
                          <span>{line.result}</span>
                        </div>
                      );
                    } else {
                      return (
                        <div key={i} className="text-[#9ca3af]">
                          <span className="text-[#555555]">{line.timestamp} </span>
                          <span className="text-[#4ade80]">→ </span>
                          <span className="text-[#6b7280]">{line.result}</span>
                        </div>
                      );
                    }
                  })}
                </div>
              )}
            </div>
          )}

          {/* Tool calls badges */}
          {msg.toolCalls && msg.toolCalls.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {msg.toolCalls.map((tool, i) => (
                <span
                  key={i}
                  className="text-[10px] px-1.5 py-0.5 border border-[rgba(0,212,255,0.2)] text-[rgba(0,212,255,0.7)]"
                >
                  [{tool}]
                </span>
              ))}
            </div>
          )}

          {/* Content */}
          <div className="text-[15px] leading-[1.7] tracking-[0.01em] text-[#e0e0e0] whitespace-pre-wrap">
            {msg.content}
            {/* Streaming cursor */}
            {isStreaming && !msg.content && (
              <span className="inline-block w-[7px] h-[16px] bg-[rgba(0,212,255,0.5)] cursor-blink ml-0.5" />
            )}
            {isStreaming && msg.content && (
              <span className="inline-block w-[6px] h-[15px] bg-[rgba(0,212,255,0.5)] cursor-blink ml-0.5 align-middle" />
            )}
          </div>

          {/* Response metadata */}
          {msg.responseTime && !isStreaming && (
            <div className="mt-2 text-[10px] text-[#555555] flex items-center gap-2">
              <span>{msg.responseTime}ms</span>
              {msg.tokenCount ? (
                <>
                  <span className="text-[#444444]">·</span>
                  <span>~{msg.tokenCount} tokens</span>
                </>
              ) : null}
              {hasThinkingSteps && (
                <>
                  <span className="text-[#444444]">·</span>
                  <span>{msg.thinkingSteps!.length} pasos de pensamiento</span>
                </>
              )}
              {hasTerminalLines && (
                <>
                  <span className="text-[#444444]">·</span>
                  <span>{msg.terminalLines!.length} ejecuciones</span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function ZAIInterface() {
  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("qwen3:4b");
  const [status, setStatus] = useState<SystemStatus>({
    connected: false,
    models: [],
    modelCount: 0,
  });
  const [uptime, setUptime] = useState(0);
  const [sessionStats, setSessionStats] = useState<SessionStats>({
    messageCount: 0,
    toolsUsed: 0,
    avgResponseTime: 0,
    totalTokens: 0,
  });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [expandedThinking, setExpandedThinking] = useState<Record<string, boolean>>({});
  const [expandedTerminal, setExpandedTerminal] = useState<Record<string, boolean>>({});
  const [isMobile, setIsMobile] = useState(false);
  const [useAgent, setUseAgent] = useState(true);

  // v17 Sidebar data
  const [sidebarData, setSidebarData] = useState<SidebarData>({
    plan: null,
    skills: [],
    tools: [],
    browserStatus: null,
    orchestratorStatus: null,
    loading: true,
    error: null,
  });

  // v17 Plan modal
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [planCreating, setPlanCreating] = useState(false);

  // v17 Sidebar section collapse
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  const toggleSection = (section: string) => {
    setCollapsedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  // Refs
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const responseTimesRef = useRef<number[]>([]);

  // ─── Detect Mobile ──────────────────────────────────────────────────────

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Close sidebar by default on mobile
  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [isMobile]);

  // ─── Fetch Status ────────────────────────────────────────────────────────

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      setStatus(data);
      if (data.connected && data.models.length > 0) {
        setSelectedModel((prev) => {
          if (data.models.find((m: OllamaModel) => m.name === prev)) return prev;
          return data.models[0].name;
        });
      }
    } catch {
      setStatus({ connected: false, agentAvailable: false, models: [], modelCount: 0, error: "Failed to fetch" });
    }
  }, []);

  // ─── Fetch Sidebar Data (v17) ────────────────────────────────────────────

  const fetchSidebarData = useCallback(async () => {
    setSidebarData((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const results = await Promise.allSettled([
        fetch("/api/plan").then((r) => r.json()),
        fetch("/api/skills").then((r) => r.json()),
        fetch("/api/tools").then((r) => r.json()),
      ]);

      const planData = results[0].status === "fulfilled" ? results[0].value : null;
      const skillsData = results[1].status === "fulfilled" ? results[1].value : null;
      const toolsData = results[2].status === "fulfilled" ? results[2].value : null;

      setSidebarData({
        plan: planData && !planData.error ? planData : null,
        skills: Array.isArray(skillsData?.skills) ? skillsData.skills : Array.isArray(skillsData) ? skillsData : [],
        tools: Array.isArray(toolsData?.tools) ? toolsData.tools : Array.isArray(toolsData) ? toolsData : [],
        browserStatus: planData?.browser ? { active: true, ...planData.browser } : null,
        orchestratorStatus: planData?.orchestrator ? { running: true, ...planData.orchestrator } : null,
        loading: false,
        error: null,
      });
    } catch (error) {
      setSidebarData((prev) => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : "Failed to fetch sidebar data",
      }));
    }
  }, []);

  // ─── Create Plan (v17) ──────────────────────────────────────────────────

  const createPlan = async (goal: string, taskType: string) => {
    setPlanCreating(true);
    try {
      const res = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal, task_type: taskType }),
      });
      const data = await res.json();

      if (data.success || data.active) {
        await fetchSidebarData();
        setPlanModalOpen(false);
      }
    } catch {
      // Error handled silently - sidebar will show stale data
    } finally {
      setPlanCreating(false);
    }
  };

  // ─── Effects ─────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  useEffect(() => {
    fetchSidebarData();
    const interval = setInterval(fetchSidebarData, 10000);
    return () => clearInterval(interval);
  }, [fetchSidebarData]);

  useEffect(() => {
    const timer = setInterval(() => setUptime((prev) => prev + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ─── Auto-select first model ────────────────────────────────────────────

  const lastAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  }, [messages]);

  // ─── Send Message ───────────────────────────────────────────────────────

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: input.trim(),
      timestamp: Date.now(),
    };

    const assistantId = generateId();
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsLoading(true);

    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    const startTime = Date.now();

    const ollamaMessages = [...messages, userMessage].map((m) => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: ollamaMessages, model: selectedModel, useAgent }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ error: "Unknown error" }));
        let errorMsg = errorData.error || "Unknown error";
        if (errorData.bridgeRequired) {
          errorMsg = `AGENT mode requires the bridge. Run: python bridge_api.py`;
        }
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: errorMsg, isStreaming: false, responseTime: Date.now() - startTime }
              : m
          )
        );
        setIsLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setIsLoading(false);
        return;
      }

      const decoder = new TextDecoder();
      let fullContent = "";
      let thinkingContent = "";
      let isThinking = false;
      let toolCalls: string[] = [];
      let tokenCount = 0;
      let thinkingSteps: ThinkingStep[] = [];
      let terminalLines: TerminalLine[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n").filter((line) => line.startsWith("data: "));

        for (const line of lines) {
          const data = line.slice(6);
          if (data === "[DONE]") continue;

          try {
            const parsed = JSON.parse(data);
            if (parsed.error) {
              fullContent += `\nError: ${parsed.error}`;
              break;
            }

            // Bridge agent events (type field present)
            if (parsed.type) {
              if (parsed.type === "text") {
                const content = parsed.data || "";
                if (content.includes("<think")) {
                  isThinking = true;
                }
                if (isThinking) {
                  thinkingContent += content;
                  if (content.includes("</think")) {
                    isThinking = false;
                  }
                } else {
                  fullContent += content;
                }
                tokenCount++;
              } else if (parsed.type === "thinking") {
                // v15: Thinking event from agent
                const step: ThinkingStep = {
                  phase: parsed.data?.phase || "unknown",
                  message: parsed.data?.message || "",
                  iteration: parsed.data?.iteration || 0,
                  confidence: parsed.data?.confidence || 0,
                  tool: parsed.data?.tool,
                  success: parsed.data?.success,
                  timestamp: new Date().toLocaleTimeString(),
                };
                thinkingSteps = [...thinkingSteps, step];
              } else if (parsed.type === "tool_start") {
                const toolName = parsed.data?.name || "unknown";
                toolCalls = [...new Set([...toolCalls, toolName])];
                // Add terminal command line
                const termLine: TerminalLine = {
                  type: "command",
                  tool: toolName,
                  params: parsed.data?.arguments || parsed.data?.params,
                  timestamp: new Date().toLocaleTimeString(),
                };
                terminalLines = [...terminalLines, termLine];
              } else if (parsed.type === "tool_result") {
                // Tool completed - add terminal output line
                const toolName = parsed.data?.tool?.name || "unknown";
                const resultStr = typeof parsed.data?.result === "string"
                  ? parsed.data.result.slice(0, 300)
                  : JSON.stringify(parsed.data?.result).slice(0, 300);
                const hasError = resultStr.includes("ERROR") || resultStr.includes("Error");
                const termLine: TerminalLine = {
                  type: hasError ? "error" : "output",
                  tool: toolName,
                  result: resultStr,
                  timestamp: new Date().toLocaleTimeString(),
                };
                terminalLines = [...terminalLines, termLine];
              } else if (parsed.type === "meta") {
                // Metacognition event - we could display this
              } else if (parsed.type === "done") {
                // Agent finished
              } else if (parsed.type === "error") {
                fullContent += `\nError: ${parsed.data}`;
              }
            } else {
              // Direct Ollama format (no type field)
              const content = parsed.message?.content || "";
              tokenCount++;

              if (content.includes("<think")) {
                isThinking = true;
              }

              if (isThinking) {
                thinkingContent += content;
                if (content.includes("</think")) {
                  isThinking = false;
                }
              } else {
                fullContent += content;
              }

              // Detect tool calls in text
              const toolMatches = content.match(/\[([a-z_]+)\]/g);
              if (toolMatches) {
                toolCalls = [...new Set([...toolCalls, ...toolMatches.map((t) => t.slice(1, -1))])];
              }
            }
          } catch {
            // Skip malformed JSON
          }
        }

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: fullContent,
                  thinking: thinkingContent || undefined,
                  thinkingSteps: thinkingSteps.length > 0 ? thinkingSteps : undefined,
                  terminalLines: terminalLines.length > 0 ? terminalLines : undefined,
                  toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                  tokenCount,
                }
              : m
          )
        );
      }

      const responseTime = Date.now() - startTime;
      responseTimesRef.current.push(responseTime);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, responseTime, isStreaming: false } : m
        )
      );

      setSessionStats((prev) => ({
        messageCount: prev.messageCount + 1,
        toolsUsed: prev.toolsUsed + toolCalls.length,
        avgResponseTime:
          responseTimesRef.current.length > 0
            ? Math.round(responseTimesRef.current.reduce((a, b) => a + b, 0) / responseTimesRef.current.length)
            : 0,
        totalTokens: prev.totalTokens + tokenCount,
      }));
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : "Unknown error";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `Connection error: ${errMsg}`, isStreaming: false, responseTime: Date.now() - startTime }
            : m
        )
      );
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  // ─── Handle Key Press ───────────────────────────────────────────────────

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ─── Toggle Thinking ────────────────────────────────────────────────────

  const toggleThinking = (id: string) => {
    setExpandedThinking((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // ─── Clear Chat ─────────────────────────────────────────────────────────

  const clearChat = () => {
    setMessages([]);
    setSessionStats({ messageCount: 0, toolsUsed: 0, avgResponseTime: 0, totalTokens: 0 });
    responseTimesRef.current = [];
  };

  // ─── Computed: Plan Progress ────────────────────────────────────────────

  const planProgress = useMemo(() => {
    const plan = sidebarData.plan;
    if (!plan?.tasks || plan.tasks.length === 0) return 0;
    const completed = plan.tasks.filter((t) => t.status === "completed").length;
    return Math.round((completed / plan.tasks.length) * 100);
  }, [sidebarData.plan]);

  // ─── Computed: Tools by Category ────────────────────────────────────────

  const toolsByCategory = useMemo(() => {
    const categories: Record<string, ToolInfo[]> = {};
    for (const tool of sidebarData.tools) {
      const cat = tool.category || "General";
      if (!categories[cat]) categories[cat] = [];
      categories[cat].push(tool);
    }
    return categories;
  }, [sidebarData.tools]);

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="h-screen flex flex-col bg-[#000000] text-[#e0e0e0] overflow-hidden" style={{ fontFamily: "var(--font-geist-mono), 'JetBrains Mono', 'Fira Code', ui-monospace, monospace" }}>
      {/* ─── Top Bar ─────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between h-9 px-4 border-b border-[rgba(255,255,255,0.06)] shrink-0 select-none">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 bg-[rgba(0,212,255,0.4)]" />
            <span className="text-[11px] tracking-[0.3em] text-[#e0e0e0] font-bold">ZAI</span>
          </div>
          <span className="text-[10px] text-[#333333]">│</span>
          <span className="text-[11px] text-[#555555]">{selectedModel}</span>
          <div className="flex items-center gap-1.5 ml-1">
            <Circle
              size={5}
              className={status.connected ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff3333] text-[#ff3333]"}
            />
            <span className="text-[10px] text-[#666666] tracking-wider">
              {status.connected ? "CONNECTED" : "OFFLINE"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Agent mode toggle */}
          <button
            onClick={() => setUseAgent(!useAgent)}
            className={`text-[10px] tracking-wider px-2.5 py-0.5 border transition-colors duration-150 ${
              useAgent
                ? "text-[#00d4ff] border-[rgba(0,212,255,0.25)] bg-[rgba(0,212,255,0.06)]"
                : "text-[#555555] border-[rgba(255,255,255,0.06)] hover:text-[#777777] hover:border-[rgba(255,255,255,0.1)]"
            }`}
            title={useAgent ? "Full agent mode (ReAct + Tools)" : "Simple chat mode (no tools)"}
          >
            {useAgent ? "AGENT" : "CHAT"}
          </button>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="text-[10px] text-[#555555] hover:text-[#777777] transition-colors px-2 py-0.5 border border-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.1)]"
            >
              CLEAR
            </button>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 text-[#555555] hover:text-[#e0e0e0] transition-colors duration-150"
            aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            {sidebarOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
          </button>
        </div>
      </header>

      {/* ─── Main Content ────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* ─── Chat Area ────────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-4 animate-fade-in select-none">
                {/* ASCII-art style logo */}
                <div className="text-[11px] leading-[1.4] text-[#2a2a2a] tracking-wider">
                  <div>╔══════════════╗</div>
                  <div>║ &nbsp; Z A I &nbsp; &nbsp; &nbsp; ║</div>
                  <div>╚══════════════╝</div>
                </div>
                <div className="h-px w-16 bg-[rgba(0,212,255,0.15)]" />
                <div className="text-[11px] text-[#3a3a3a] max-w-sm text-center leading-[1.7]">
                  Local AI agent interface.
                  <br />
                  <span className="text-[#333333]">All processing runs on your machine via Ollama.</span>
                </div>
                <div className="flex items-center gap-4 mt-2">
                  <div className="flex items-center gap-1.5">
                    <Circle size={4} className={status.connected ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff3333] text-[#ff3333]"} />
                    <span className="text-[10px] text-[#444444]">
                      {status.connected ? "OLLAMA CONNECTED" : "OLLAMA OFFLINE"}
                    </span>
                  </div>
                  <span className="text-[10px] text-[#333333]">│</span>
                  <span className="text-[10px] text-[#444444]">{selectedModel}</span>
                </div>
                {!status.connected && (
                  <div className="mt-1 px-4 py-2 border border-[rgba(255,51,51,0.15)] text-[9px] text-[#ff3333]">
                    Start Ollama: ollama serve
                  </div>
                )}
                {useAgent && !status.agentAvailable && status.connected && (
                  <div className="mt-1 px-4 py-2 border border-[rgba(255,136,0,0.2)] text-[10px] text-[#ff8800] leading-[1.6]">
                    AGENT mode is ON but Bridge is not running.<br />
                    Tools won&apos;t work. Start: <span className="text-[#ffaa33]">python bridge_api.py</span>
                  </div>
                )}
              </div>
            )}

            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                msg={msg}
                isLastAssistant={msg.id === lastAssistantId}
                isLoading={isLoading}
                expandedThinking={expandedThinking}
                toggleThinking={toggleThinking}
                expandedTerminal={expandedTerminal}
                toggleTerminal={(id) => setExpandedTerminal(prev => ({...prev, [id]: !prev[id]}))}
              />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* ─── Input Area ──────────────────────────────────────────────── */}
          {/* Bridge warning bar */}
          {useAgent && !status.agentAvailable && status.connected && (
            <div className="px-5 py-1.5 border-t border-[rgba(255,136,0,0.15)] bg-[rgba(255,136,0,0.03)] text-[10px] text-[#ff8800] flex items-center gap-2">
              <Circle size={4} className="fill-[#ff8800] text-[#ff8800]" />
              <span>Bridge not running — tools disabled. Start: python bridge_api.py</span>
            </div>
          )}
          <div className="shrink-0 border-t border-[rgba(255,255,255,0.06)]">
            <div className="flex items-end gap-3 px-5 py-3">
              <div className="text-[12px] text-[#555555] pb-1 select-none">{">"}</div>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={status.connected ? "Enter message..." : "Ollama not connected"}
                disabled={!status.connected}
                rows={1}
                className="flex-1 bg-transparent text-[15px] text-[#e0e0e0] placeholder-[#3a3a3a] resize-none outline-none min-h-[22px] max-h-[140px] leading-[1.6] disabled:opacity-20"
                style={{ fontFamily: "inherit" }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = "auto";
                  target.style.height = Math.min(target.scrollHeight, 120) + "px";
                }}
              />
              {/* v17 Plan button */}
              {useAgent && (
                <button
                  onClick={() => setPlanModalOpen(true)}
                  disabled={!status.connected || !status.agentAvailable}
                  className="pb-1 text-[#555555] hover:text-[rgba(0,212,255,0.6)] disabled:opacity-10 disabled:hover:text-[#555555] transition-colors duration-150 shrink-0"
                  title="Create a plan"
                >
                  <Target size={15} />
                </button>
              )}
              <button
                onClick={sendMessage}
                disabled={!input.trim() || isLoading || !status.connected}
                className="pb-1 text-[#555555] hover:text-[rgba(0,212,255,0.6)] disabled:opacity-10 disabled:hover:text-[#555555] transition-colors duration-150 shrink-0"
                aria-label="Send message"
              >
                {isLoading ? (
                  <Activity size={15} className="animate-spin" />
                ) : (
                  <Send size={15} />
                )}
              </button>
            </div>
          </div>
        </main>

        {/* ─── Sidebar Overlay (mobile) ──────────────────────────────────── */}
        {isMobile && sidebarOpen && (
          <div
            className="absolute inset-0 bg-[rgba(0,0,0,0.5)] z-10"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* ─── Sidebar ───────────────────────────────────────────────────── */}
        <aside
          className={`${
            sidebarOpen ? "w-72" : "w-0"
          } ${isMobile ? "absolute right-0 top-0 bottom-0 z-20" : "relative"
          } shrink-0 border-l border-[rgba(255,255,255,0.06)] bg-[#050505] overflow-hidden transition-all duration-200`}
        >
          <div className="w-72 h-full overflow-y-auto px-4 py-4 space-y-5">

            {/* ═══ v17: PLAN STATUS ══════════════════════════════════════════ */}
            <section>
              <button
                onClick={() => toggleSection("plan")}
                className="flex items-center gap-1.5 mb-3 w-full"
              >
                <Target size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase text-left">Plan Status</h3>
                <span className="ml-auto">
                  {collapsedSections["plan"] ? (
                    <ChevronRight size={9} className="text-[#444444]" />
                  ) : (
                    <ChevronDown size={9} className="text-[#444444]" />
                  )}
                </span>
              </button>
              {!collapsedSections["plan"] && (
                <div className="space-y-2.5">
                  {sidebarData.loading && !sidebarData.plan ? (
                    <div className="flex items-center gap-2 text-[10px] text-[#444444]">
                      <Loader2 size={10} className="animate-spin text-[#555555]" />
                      <span>Loading plan...</span>
                    </div>
                  ) : sidebarData.plan?.active ? (
                    <>
                      {/* Goal */}
                      <div>
                        <span className="text-[10px] text-[#505050]">GOAL</span>
                        <p className="text-[11px] text-[#999999] mt-0.5 leading-[1.5] line-clamp-2">
                          {sidebarData.plan.goal}
                        </p>
                      </div>
                      {/* Progress bar */}
                      {sidebarData.plan.tasks && sidebarData.plan.tasks.length > 0 && (
                        <div>
                          <div className="flex justify-between items-center mb-1.5">
                            <span className="text-[10px] text-[#505050]">PROGRESS</span>
                            <span className="text-[10px] text-[#00d4ff] tabular-nums">{planProgress}%</span>
                          </div>
                          <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
                            <div
                              className="h-full bg-[rgba(0,212,255,0.5)] transition-all duration-500"
                              style={{ width: `${planProgress}%` }}
                            />
                          </div>
                        </div>
                      )}
                      {/* Task list */}
                      {sidebarData.plan.tasks && sidebarData.plan.tasks.length > 0 && (
                        <div className="space-y-1 max-h-48 overflow-y-auto">
                          {sidebarData.plan.tasks.map((task, i) => {
                            const isCurrent = i === sidebarData.plan?.current_task_index;
                            const statusIcon = task.status === "completed" ? (
                              <CheckCircle2 size={10} className="text-[#4ade80] shrink-0" />
                            ) : task.status === "in_progress" || isCurrent ? (
                              <CircleDot size={10} className="text-[#00d4ff] shrink-0 animate-pulse" />
                            ) : task.status === "failed" ? (
                              <AlertCircle size={10} className="text-[#f87171] shrink-0" />
                            ) : (
                              <CircleEllipsis size={10} className="text-[#444444] shrink-0" />
                            );
                            return (
                              <div
                                key={task.id || i}
                                className={`flex items-start gap-1.5 px-2 py-1.5 border transition-colors ${
                                  isCurrent
                                    ? "border-[rgba(0,212,255,0.2)] bg-[rgba(0,212,255,0.03)]"
                                    : "border-transparent"
                                }`}
                              >
                                {statusIcon}
                                <span
                                  className={`text-[10px] leading-[1.4] ${
                                    task.status === "completed"
                                      ? "text-[#4ade80] line-through opacity-60"
                                      : isCurrent
                                        ? "text-[#e0e0e0]"
                                        : "text-[#666666]"
                                  }`}
                                >
                                  {task.description}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {/* Task type badge */}
                      {sidebarData.plan.task_type && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[9px] text-[#505050]">TYPE</span>
                          <span className="text-[9px] px-1.5 py-0.5 border border-[rgba(0,212,255,0.15)] text-[rgba(0,212,255,0.6)]">
                            {sidebarData.plan.task_type}
                          </span>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-[10px] text-[#3a3a3a]">
                      No active plan
                    </div>
                  )}
                </div>
              )}
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* ═══ v17: SKILLS ══════════════════════════════════════════════ */}
            <section>
              <button
                onClick={() => toggleSection("skills")}
                className="flex items-center gap-1.5 mb-3 w-full"
              >
                <Sparkles size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase text-left">Skills</h3>
                {sidebarData.skills.length > 0 && (
                  <span className="text-[9px] text-[#505050] ml-auto mr-2">{sidebarData.skills.length}</span>
                )}
                {collapsedSections["skills"] ? (
                  <ChevronRight size={9} className="text-[#444444]" />
                ) : (
                  <ChevronDown size={9} className="text-[#444444]" />
                )}
              </button>
              {!collapsedSections["skills"] && (
                <div className="space-y-2">
                  {sidebarData.loading && sidebarData.skills.length === 0 ? (
                    <div className="flex items-center gap-2 text-[10px] text-[#444444]">
                      <Loader2 size={10} className="animate-spin text-[#555555]" />
                      <span>Loading skills...</span>
                    </div>
                  ) : sidebarData.skills.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {sidebarData.skills.map((skill, i) => (
                        <span
                          key={skill.name || i}
                          className={`text-[9px] px-2 py-0.5 border transition-colors ${
                            skill.loaded !== false
                              ? "border-[rgba(0,255,136,0.2)] text-[rgba(0,255,136,0.7)] bg-[rgba(0,255,136,0.03)]"
                              : "border-[rgba(255,255,255,0.06)] text-[#555555]"
                          }`}
                          title={skill.description || skill.name}
                        >
                          {skill.name}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[10px] text-[#3a3a3a]">
                      No skills loaded
                    </div>
                  )}
                </div>
              )}
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* ═══ v17: TOOLS ═══════════════════════════════════════════════ */}
            <section>
              <button
                onClick={() => toggleSection("tools")}
                className="flex items-center gap-1.5 mb-3 w-full"
              >
                <Wrench size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase text-left">Tools</h3>
                {sidebarData.tools.length > 0 && (
                  <span className="text-[9px] text-[#505050] ml-auto mr-2">{sidebarData.tools.length}</span>
                )}
                {collapsedSections["tools"] ? (
                  <ChevronRight size={9} className="text-[#444444]" />
                ) : (
                  <ChevronDown size={9} className="text-[#444444]" />
                )}
              </button>
              {!collapsedSections["tools"] && (
                <div className="space-y-2.5">
                  {sidebarData.loading && sidebarData.tools.length === 0 ? (
                    <div className="flex items-center gap-2 text-[10px] text-[#444444]">
                      <Loader2 size={10} className="animate-spin text-[#555555]" />
                      <span>Loading tools...</span>
                    </div>
                  ) : sidebarData.tools.length > 0 ? (
                    <div className="space-y-3 max-h-64 overflow-y-auto">
                      {Object.entries(toolsByCategory).map(([category, tools]) => (
                        <div key={category}>
                          <div className="text-[9px] tracking-[0.15em] text-[#444444] uppercase mb-1.5">
                            {category}
                          </div>
                          <div className="space-y-0.5">
                            {tools.map((tool, i) => (
                              <div
                                key={tool.name || i}
                                className="flex items-center gap-1.5 px-2 py-1 hover:bg-[rgba(255,255,255,0.015)] transition-colors"
                              >
                                <span className="text-[10px] text-[rgba(0,212,255,0.6)] shrink-0">▸</span>
                                <span className="text-[10px] text-[#888888] truncate">{tool.name}</span>
                                {tool.description && (
                                  <span className="text-[9px] text-[#3a3a3a] truncate hidden xl:inline">
                                    — {tool.description.slice(0, 40)}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[10px] text-[#3a3a3a]">
                      No tools registered
                    </div>
                  )}
                </div>
              )}
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* ═══ v17: BROWSER ═════════════════════════════════════════════ */}
            <section>
              <button
                onClick={() => toggleSection("browser")}
                className="flex items-center gap-1.5 mb-3 w-full"
              >
                <Globe size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase text-left">Browser</h3>
                {collapsedSections["browser"] ? (
                  <ChevronRight size={9} className="text-[#444444] ml-auto" />
                ) : (
                  <ChevronDown size={9} className="text-[#444444] ml-auto" />
                )}
              </button>
              {!collapsedSections["browser"] && (
                <div className="space-y-2.5">
                  {sidebarData.loading && !sidebarData.browserStatus ? (
                    <div className="flex items-center gap-2 text-[10px] text-[#444444]">
                      <Loader2 size={10} className="animate-spin text-[#555555]" />
                      <span>Loading browser status...</span>
                    </div>
                  ) : sidebarData.browserStatus?.active ? (
                    <>
                      <div className="flex justify-between items-center">
                        <span className="text-[10px] text-[#505050]">STATUS</span>
                        <div className="flex items-center gap-1.5">
                          <Circle size={4} className="fill-[#4ade80] text-[#4ade80]" />
                          <span className="text-[10px] text-[#4ade80]">Active</span>
                        </div>
                      </div>
                      {sidebarData.browserStatus.url && (
                        <div>
                          <span className="text-[10px] text-[#505050]">URL</span>
                          <p className="text-[10px] text-[#888888] mt-0.5 truncate" title={sidebarData.browserStatus.url}>
                            {sidebarData.browserStatus.url}
                          </p>
                        </div>
                      )}
                      {sidebarData.browserStatus.title && (
                        <div>
                          <span className="text-[10px] text-[#505050]">TITLE</span>
                          <p className="text-[10px] text-[#888888] mt-0.5 truncate">
                            {sidebarData.browserStatus.title}
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="flex justify-between items-center">
                        <span className="text-[10px] text-[#505050]">STATUS</span>
                        <div className="flex items-center gap-1.5">
                          <Circle size={4} className="fill-[#444444] text-[#444444]" />
                          <span className="text-[10px] text-[#555555]">Inactive</span>
                        </div>
                      </div>
                      <div className="text-[10px] text-[#3a3a3a]">
                        Browser automation not active
                      </div>
                    </>
                  )}
                </div>
              )}
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* SYSTEM */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Server size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase">System</h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">MODEL</span>
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="bg-transparent text-[10px] text-[#e0e0e0] outline-none cursor-pointer text-right appearance-none"
                    style={{ fontFamily: "inherit" }}
                  >
                    {status.models.length > 0 ? (
                      status.models.map((m) => (
                        <option key={m.name} value={m.name} className="bg-[#111111] text-[#e0e0e0]">
                          {m.name}
                        </option>
                      ))
                    ) : (
                      <option value={selectedModel} className="bg-[#111111] text-[#e0e0e0]">
                        {selectedModel}
                      </option>
                    )}
                  </select>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">HOST</span>
                  <span className="text-[11px] text-[#666666]">localhost:11434</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">STATUS</span>
                  <div className="flex items-center gap-1.5">
                    <Circle
                      size={4}
                      className={status.connected ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff3333] text-[#ff3333]"}
                    />
                    <span className="text-[10px] text-[#555555]">
                      {status.connected ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">UPTIME</span>
                  <span className="text-[11px] text-[#666666] tabular-nums">{formatUptime(uptime)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">MODE</span>
                  <span className={`text-[11px] ${useAgent ? "text-[#00d4ff]" : "text-[#666666]"}`}>
                    {useAgent ? "AGENT" : "CHAT"}
                  </span>
                </div>
                {useAgent && status.agentAvailable !== undefined && (
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[#505050]">BRIDGE</span>
                    <div className="flex items-center gap-1.5">
                      <Circle
                        size={4}
                        className={status.agentAvailable ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff8800] text-[#ff8800]"}
                      />
                      <span className="text-[11px] text-[#666666]">
                        {status.agentAvailable ? "Active" : "Inactive"}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* HARDWARE */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Cpu size={10} className="text-[#555555]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">Hardware</h3>
              </div>
              <HardwareStats />
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* SESSION */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Zap size={10} className="text-[#555555]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">Session</h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <MessageSquare size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">MESSAGES</span>
                  </div>
                  <span className="text-[11px] text-[#e0e0e0] tabular-nums">{sessionStats.messageCount}</span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Wrench size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">TOOLS</span>
                  </div>
                  <span className="text-[11px] text-[#e0e0e0] tabular-nums">{sessionStats.toolsUsed}</span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Clock size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">AVG RESP</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.avgResponseTime > 0 ? `${sessionStats.avgResponseTime}ms` : "—"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Activity size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">TOKENS</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.totalTokens > 0 ? `~${sessionStats.totalTokens}` : "—"}
                  </span>
                </div>
              </div>
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* MODELS */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <HardDrive size={10} className="text-[#555555]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">Models</h3>
                {status.connected && (
                  <span className="text-[9px] text-[#505050] ml-auto">{status.modelCount}</span>
                )}
              </div>
              <div className="space-y-0.5 max-h-52 overflow-y-auto">
                {status.connected && status.models.length > 0 ? (
                  status.models.map((model) => (
                    <button
                      key={model.name}
                      onClick={() => setSelectedModel(model.name)}
                      className={`w-full text-left px-2 py-1.5 border transition-all duration-150 ${
                        model.name === selectedModel
                          ? "border-[rgba(0,212,255,0.2)] bg-[rgba(0,212,255,0.03)]"
                          : "border-transparent hover:border-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.015)]"
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <span className={`text-[11px] truncate mr-2 ${model.name === selectedModel ? "text-[#e0e0e0]" : "text-[#666666]"}`}>
                          {model.name}
                        </span>
                        <span className="text-[9px] text-[#444444] shrink-0">
                          {formatBytes(model.size)}
                        </span>
                      </div>
                      {model.parameter_size !== "unknown" && (
                        <div className="text-[9px] text-[#3a3a3a] mt-0.5">
                          {model.parameter_size} · {model.quantization_level}
                        </div>
                      )}
                    </button>
                  ))
                ) : (
                  <div className="text-[10px] text-[#3a3a3a] px-2 py-1">
                    {status.connected ? "No models found" : "Cannot connect to Ollama"}
                  </div>
                )}
              </div>
            </section>

            {/* Footer */}
            <div className="pt-6">
              <div className="text-[8px] text-[#333333] text-center tracking-[0.4em] uppercase">
                ZAI Agent Interface v17
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* ─── Plan Modal ──────────────────────────────────────────────────── */}
      <PlanModal
        isOpen={planModalOpen}
        onClose={() => setPlanModalOpen(false)}
        onSubmit={createPlan}
        isCreating={planCreating}
      />
    </div>
  );
}
