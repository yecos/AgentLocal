"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
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
  Paperclip,
  Mic,
  MicOff,
  Square,
  X,
  AlertTriangle,
  Sparkles,
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

interface ToolCall {
  name: string;
  arguments?: Record<string, unknown>;
  result?: string;
  status: "loading" | "success" | "error";
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  toolCalls?: ToolCall[];
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

interface ToolInfo {
  name: string;
  description?: string;
  category?: string;
}

interface UploadedFile {
  name: string;
  size: number;
  type: string;
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
  return Math.random().toString(36).substring(2, 9) + Date.now().toString(36);
}

function cleanThinking(text: string): string {
  return text
    .replace(/<\/?think[^>]*>/g, "")
    .trim();
}

// ─── Tool Call Card Component ────────────────────────────────────────────────

function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const statusColors = {
    loading: "text-[#ffd93d] border-[rgba(255,217,61,0.2)]",
    success: "text-[#00ff88] border-[rgba(0,255,136,0.2)]",
    error: "text-[#ff3333] border-[rgba(255,51,51,0.2)]",
  };
  const statusIcons = {
    loading: "⟳",
    success: "✓",
    error: "✗",
  };

  return (
    <div
      className={`my-1.5 border ${statusColors[toolCall.status]} bg-[rgba(255,255,255,0.02)] px-3 py-2 text-[12px]`}
    >
      <div className="flex items-center gap-2">
        <span className={`${statusColors[toolCall.status]}`}>
          {toolCall.status === "loading" ? (
            <span className="inline-block animate-spin">⟳</span>
          ) : (
            statusIcons[toolCall.status]
          )}
        </span>
        <span className="text-[#e0e0e0] font-medium">{toolCall.name}</span>
        {toolCall.arguments && Object.keys(toolCall.arguments).length > 0 && (
          <span className="text-[#777] text-[11px]">
            (
            {Object.entries(toolCall.arguments)
              .map(([k, v]) => `${k}=${String(v).slice(0, 30)}`)
              .join(", ")}
            )
          </span>
        )}
      </div>
      {toolCall.result && (
        <div className="mt-1.5 text-[11px] text-[#888] max-h-24 overflow-y-auto whitespace-pre-wrap border-l border-[rgba(255,255,255,0.06)] pl-2">
          {toolCall.result.slice(0, 500)}
        </div>
      )}
    </div>
  );
}

// ─── Hardware Stats Component (REAL data via /api/system) ──────────────────

interface SystemInfo {
  cpu_percent: number;
  ram_percent: number;
  ram_total_gb: number;
  ram_used_gb: number;
  disk_percent: number;
  disk_total_gb: number;
  disk_used_gb: number;
  gpu: {
    name: string;
    vram_total_mb: number;
    vram_used_mb: number;
    vram_free_mb: number;
    gpu_utilization: number;
  } | null;
}

function HardwareStats() {
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);

  useEffect(() => {
    const fetchSystem = async () => {
      try {
        const res = await fetch("/api/system");
        if (res.ok) {
          const data = await res.json();
          setSysInfo(data);
        }
      } catch {
        // System info not available
      }
    };
    fetchSystem();
    const interval = setInterval(fetchSystem, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  const cpu = sysInfo?.cpu_percent ?? 0;
  const mem = sysInfo?.ram_percent ?? 0;
  const disk = sysInfo?.disk_percent ?? 0;
  const gpu = sysInfo?.gpu;

  return (
    <div className="space-y-3">
      <div>
        <div className="flex justify-between items-center mb-1">
          <span className="text-[10px] text-[#505050]">GPU</span>
          <span className="text-[11px] text-[#666666]">
            {gpu ? `${gpu.gpu_utilization}%` : sysInfo ? "—" : "..."}
          </span>
        </div>
        <div className="text-[9px] text-[#444444]">
          {gpu
            ? `${gpu.name} · ${gpu.vram_used_mb}/${gpu.vram_total_mb}MB VRAM`
            : sysInfo
            ? "No GPU detected"
            : "Detecting..."}
        </div>
        {gpu && (
          <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden mt-1">
            <div
              className="h-full bg-[rgba(168,85,247,0.4)] transition-all duration-1000"
              style={{ width: `${gpu.gpu_utilization}%` }}
            />
          </div>
        )}
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <Cpu size={9} className="text-[#505050]" />
            <span className="text-[10px] text-[#505050]">CPU</span>
          </div>
          <span className="text-[10px] text-[#666666]">
            {sysInfo ? `${cpu}%` : "..."}
          </span>
        </div>
        <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
          <div
            className="h-full bg-[rgba(0,212,255,0.4)] transition-all duration-1000"
            style={{ width: sysInfo ? `${cpu}%` : "0%" }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <MemoryStick size={9} className="text-[#505050]" />
            <span className="text-[10px] text-[#505050]">MEM</span>
          </div>
          <span className="text-[10px] text-[#666666]">
            {sysInfo ? `${mem}% (${sysInfo.ram_used_gb}/${sysInfo.ram_total_gb}GB)` : "..."}
          </span>
        </div>
        <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
          <div
            className="h-full bg-[rgba(0,255,136,0.35)] transition-all duration-1000"
            style={{ width: sysInfo ? `${mem}%` : "0%" }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <HardDrive size={9} className="text-[#505050]" />
            <span className="text-[10px] text-[#505050]">DISK</span>
          </div>
          <span className="text-[10px] text-[#666666]">
            {sysInfo ? `${disk}% (${sysInfo.disk_used_gb}/${sysInfo.disk_total_gb}GB)` : "..."}
          </span>
        </div>
        <div className="h-[3px] bg-[rgba(255,255,255,0.08)] overflow-hidden">
          <div
            className="h-full bg-[rgba(255,217,61,0.35)] transition-all duration-1000"
            style={{ width: sysInfo ? `${disk}%` : "0%" }}
          />
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
}: {
  msg: Message;
  isLastAssistant: boolean;
  isLoading: boolean;
  expandedThinking: Record<string, boolean>;
  toggleThinking: (id: string) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[70%] px-3.5 py-2.5 border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] text-[14px] leading-[1.7] tracking-[0.01em] text-[#f0f0f0]">
          {msg.content}
        </div>
      </div>
    );
  }

  const isStreaming = isLastAssistant && isLoading;
  const cleanedThinking = msg.thinking ? cleanThinking(msg.thinking) : "";

  return (
    <div className="animate-fade-in">
      <div className="max-w-[85%]">
        <div className="border-l-2 border-[rgba(0,212,255,0.3)] pl-3">
          {/* Thinking section */}
          {cleanedThinking && (
            <div className="mb-2.5">
              <button
                onClick={() => toggleThinking(msg.id)}
                className="flex items-center gap-1 text-[10px] text-[#666666] hover:text-[#999999] transition-colors duration-150"
              >
                {expandedThinking[msg.id] ? (
                  <ChevronDown size={10} />
                ) : (
                  <ChevronRight size={10} />
                )}
                <Sparkles size={9} className="text-[rgba(0,212,255,0.4)]" />
                <span>thinking</span>
                <span className="text-[#555555] ml-1">
                  ({cleanedThinking.length} chars)
                </span>
              </button>
              {expandedThinking[msg.id] && (
                <div className="mt-1.5 text-[11px] leading-[1.6] text-[#555555] max-h-40 overflow-y-auto pr-2 whitespace-pre-wrap border-l border-[rgba(255,255,255,0.06)] pl-2">
                  {cleanedThinking}
                </div>
              )}
            </div>
          )}

          {/* Tool call cards */}
          {msg.toolCalls && msg.toolCalls.length > 0 && (
            <div className="mb-2">
              {msg.toolCalls.map((tool, i) => (
                <ToolCallCard key={i} toolCall={tool} />
              ))}
            </div>
          )}

          {/* Content with Markdown */}
          <div className="text-[14px] leading-[1.7] tracking-[0.01em] text-[#e0e0e0]">
            {msg.content ? (
              <ReactMarkdown
                components={{
                  code({
                    className,
                    children,
                    ...props
                  }) {
                    const match = /language-(\w+)/.exec(className || "");
                    const inline = !match;
                    return !inline ? (
                      <SyntaxHighlighter
                        style={oneDark}
                        language={match[1]}
                        PreTag="div"
                        className="!bg-[rgba(255,255,255,0.04)] !border !border-[rgba(255,255,255,0.06)] !rounded-sm !my-2 !text-[12px]"
                      >
                        {String(children).replace(/\n$/, "")}
                      </SyntaxHighlighter>
                    ) : (
                      <code
                        className="px-1 py-0.5 bg-[rgba(255,255,255,0.06)] text-[#00d4ff] text-[13px]"
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                  p({ children }) {
                    return (
                      <p className="mb-2 last:mb-0 leading-[1.7]">{children}</p>
                    );
                  },
                  ul({ children }) {
                    return <ul className="mb-2 ml-4 list-disc">{children}</ul>;
                  },
                  ol({ children }) {
                    return (
                      <ol className="mb-2 ml-4 list-decimal">{children}</ol>
                    );
                  },
                  li({ children }) {
                    return <li className="mb-1">{children}</li>;
                  },
                  h1({ children }) {
                    return (
                      <h1 className="text-xl font-bold mb-2 text-[#00d4ff]">
                        {children}
                      </h1>
                    );
                  },
                  h2({ children }) {
                    return (
                      <h2 className="text-lg font-bold mb-2 text-[#00d4ff]">
                        {children}
                      </h2>
                    );
                  },
                  h3({ children }) {
                    return (
                      <h3 className="text-base font-bold mb-1 text-[#00d4ff]">
                        {children}
                      </h3>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-[#00d4ff] pl-3 my-2 text-[#999]">
                        {children}
                      </blockquote>
                    );
                  },
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        className="text-[#00d4ff] underline hover:text-[#33ddff]"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {children}
                      </a>
                    );
                  },
                  table({ children }) {
                    return (
                      <table className="border-collapse my-2 w-full">
                        {children}
                      </table>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border border-[rgba(255,255,255,0.1)] px-2 py-1 text-left text-[#00d4ff]">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border border-[rgba(255,255,255,0.1)] px-2 py-1">
                        {children}
                      </td>
                    );
                  },
                  hr() {
                    return (
                      <hr className="border-[rgba(255,255,255,0.08)] my-3" />
                    );
                  },
                  pre({ children }) {
                    return <pre className="!bg-transparent !m-0 !p-0">{children}</pre>;
                  },
                }}
              >
                {msg.content}
              </ReactMarkdown>
            ) : null}

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
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <>
                  <span className="text-[#444444]">·</span>
                  <span>{msg.toolCalls.length} tool calls</span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Welcome Screen Component ────────────────────────────────────────────────

function WelcomeScreen({
  status,
  selectedModel,
  useAgent,
}: {
  status: SystemStatus;
  selectedModel: string;
  useAgent: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 animate-fade-in select-none">
      {/* ASCII-art style logo */}
      <div className="text-[13px] leading-[1.4] text-[rgba(0,212,255,0.15)] tracking-[0.2em] font-bold">
        <div className="text-center">
          ┏┳┓┏┓┏┓┏┓
        </div>
        <div className="text-center">
          ┃ ┣ ┣┫┗┓
        </div>
        <div className="text-center">
          ┻ ┗┛┗┛┗┛
        </div>
      </div>
      <div className="h-px w-20 bg-[rgba(0,212,255,0.2)]" />
      <div className="text-[11px] text-[#3a3a3a] max-w-sm text-center leading-[1.7]">
        Local AI agent interface.
        <br />
        <span className="text-[#333333]">
          All processing runs on your machine via Ollama. 100% local, no cloud.
        </span>
      </div>
      <div className="flex items-center gap-4 mt-2">
        <div className="flex items-center gap-1.5">
          <Circle
            size={4}
            className={
              status.connected
                ? "fill-[#00ff88] text-[#00ff88]"
                : "fill-[#ff3333] text-[#ff3333]"
            }
          />
          <span className="text-[10px] text-[#444444]">
            {status.connected ? "OLLAMA CONNECTED" : "OLLAMA OFFLINE"}
          </span>
        </div>
        <span className="text-[10px] text-[#333333]">│</span>
        <span className="text-[10px] text-[#444444]">{selectedModel}</span>
        <span className="text-[10px] text-[#333333]">│</span>
        <span className="text-[10px] text-[#444444]">
          {useAgent ? "AGENT" : "CHAT"}
        </span>
      </div>
      {!status.connected && (
        <div className="mt-1 px-4 py-2 border border-[rgba(255,51,51,0.15)] text-[9px] text-[#ff3333]">
          Start Ollama: ollama serve
        </div>
      )}
      {useAgent && !status.agentAvailable && status.connected && (
        <div className="mt-1 px-4 py-2 border border-[rgba(255,217,61,0.2)] text-[10px] text-[#ffd93d] leading-[1.6] flex items-center gap-2">
          <AlertTriangle size={12} className="shrink-0" />
          <span>
            AGENT mode requires Bridge. Start:{" "}
            <span className="text-[#ffaa33]">python bridge_api.py</span>
          </span>
        </div>
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function AgentLocalInterface() {
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
  const [expandedThinking, setExpandedThinking] = useState<
    Record<string, boolean>
  >({});
  const [isMobile, setIsMobile] = useState(false);
  const [useAgent, setUseAgent] = useState(true);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [tools, setTools] = useState<ToolInfo[]>([]);

  // Refs
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const responseTimesRef = useRef<number[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);

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
          if (data.models.find((m: OllamaModel) => m.name === prev))
            return prev;
          return data.models[0].name;
        });
      }
    } catch {
      setStatus({
        connected: false,
        agentAvailable: false,
        models: [],
        modelCount: 0,
        error: "Failed to fetch",
      });
    }
  }, []);

  // ─── Fetch Tools ─────────────────────────────────────────────────────────

  const fetchTools = useCallback(async () => {
    try {
      const res = await fetch("/api/tools");
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.tools)) {
          setTools(
            data.tools.map((t: any) => ({
              name: t.name || t,
              description: t.description || "",
              category: t.category || "general",
            }))
          );
        } else if (Array.isArray(data)) {
          setTools(
            data.map((t: any) => ({
              name: t.name || t,
              description: t.description || "",
              category: t.category || "general",
            }))
          );
        }
      }
    } catch {
      // Tools not available - that's fine
    }
  }, []);

  // ─── Effects ─────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  useEffect(() => {
    fetchTools();
    const interval = setInterval(fetchTools, 30000);
    return () => clearInterval(interval);
  }, [fetchTools]);

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

  // ─── Group Tools by Category ────────────────────────────────────────────

  const toolsByCategory = useMemo(() => {
    const groups: Record<string, ToolInfo[]> = {};
    for (const tool of tools) {
      const cat = tool.category || "general";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(tool);
    }
    return groups;
  }, [tools]);

  // ─── File Upload ────────────────────────────────────────────────────────

  const fileObjectsRef = useRef<File[]>([]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    const newFiles: UploadedFile[] = [];
    const newFileObjects: File[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      newFiles.push({
        name: file.name,
        size: file.size,
        type: file.type,
      });
      newFileObjects.push(file);
    }
    setUploadedFiles((prev) => [...prev, ...newFiles]);
    fileObjectsRef.current = [...fileObjectsRef.current, ...newFileObjects];

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const removeFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
    fileObjectsRef.current = fileObjectsRef.current.filter((_, i) => i !== index);
  };

  const uploadFiles = async (): Promise<string[]> => {
    if (uploadedFiles.length === 0) return [];
    if (fileObjectsRef.current.length === 0) return uploadedFiles.map((f) => f.name);

    try {
      const formData = new FormData();
      for (const file of fileObjectsRef.current) {
        formData.append("files", file);
      }
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const names = (data.files || []).map((f: { name: string }) => f.name);
        return names.length > 0 ? names : uploadedFiles.map((f) => f.name);
      }
    } catch {
      // Upload failed, still include file names in the message
    }

    return uploadedFiles.map((f) => f.name);
  };

  // ─── Voice Input ────────────────────────────────────────────────────────

  const toggleVoiceInput = useCallback(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      // Web Speech API not available
      return;
    }

    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsRecording(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => (prev ? prev + " " + transcript : transcript));
      setIsRecording(false);
    };

    recognition.onerror = () => {
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
  }, [isRecording]);

  // ─── Stop Generation ────────────────────────────────────────────────────

  const stopGeneration = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    // Also request server-side cancellation (B7)
    try {
      await fetch("/api/chat/cancel", { method: "POST" });
    } catch {
      // Cancel request failed - client abort already sent
    }
  }, []);

  // ─── Send Message ───────────────────────────────────────────────────────

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    // Handle file uploads first
    let fileNames: string[] = [];
    if (uploadedFiles.length > 0) {
      fileNames = await uploadFiles();
    }

    const userContent =
      fileNames.length > 0
        ? `${input.trim()}\n\n[Attached files: ${fileNames.join(", ")}]`
        : input.trim();

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: userContent,
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
    setUploadedFiles([]);
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

    // Create AbortController for this request
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: ollamaMessages,
          model: selectedModel,
          useAgent,
        }),
        signal: abortController.signal,
      });

      if (!res.ok) {
        const errorData = await res
          .json()
          .catch(() => ({ error: "Unknown error" }));
        let errorMsg = errorData.error || "Unknown error";
        if (errorData.bridgeRequired) {
          errorMsg = `AGENT mode requires the bridge. Run: python bridge_api.py`;
        }
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: errorMsg,
                  isStreaming: false,
                  responseTime: Date.now() - startTime,
                }
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
      let toolCalls: ToolCall[] = [];
      let tokenCount = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk
          .split("\n")
          .filter((line) => line.startsWith("data: "));

        for (const line of lines) {
          const data = line.slice(6);
          if (data === "[DONE]") continue;

          try {
            const parsed = JSON.parse(data);
            if (parsed.error) {
              // v5: Filter out raw JSON key names from error messages
              let errVal = String(parsed.error);
              if (['"pensamiento"', '"accion"', '"respuesta_final"', '"params"'].some(k => errVal.includes(k))) {
                errVal = 'Error procesando respuesta del modelo';
              }
              fullContent += `\nError: ${errVal}`;
              break;
            }

            // Bridge agent events (type field present)
            if (parsed.type) {
              if (parsed.type === "text") {
                let content = parsed.data || "";
                // v5: More robust filtering of internal agent JSON
                // (pensamiento, accion, respuesta_final, params)
                // Check if entire content is internal JSON - try to extract useful content
                const trimmed = content.trim();
                if (trimmed.startsWith('{')) {
                  try {
                    const jsonObj = JSON.parse(trimmed);
                    // Extract useful content: respuesta_final > pensamiento
                    content = jsonObj.respuesta_final || jsonObj.pensamiento || '';
                    if (!content) continue;
                  } catch {
                    // Partial/incomplete JSON - check if it's internal agent JSON
                    if (trimmed.includes('"pensamiento"') || trimmed.includes('"accion"') || trimmed.includes('"respuesta_final"')) {
                      // Don't show partial internal JSON to user
                      continue;
                    }
                  }
                }
                // Additional cleanup: remove any residual JSON key fragments
                content = content.replace(/"?pensamiento"?\s*:\s*"?[^",}]*"?\s*,?\s*/g, '');
                content = content.replace(/"?accion"?\s*:\s*"?[^",}]*"?\s*,?\s*/g, '');
                content = content.replace(/"?respuesta_final"?\s*:\s*"?[^",}]*"?\s*,?\s*/g, '');
                // Remove literal key names that might leak through
                content = content.replace(/"(?:pensamiento|accion|respuesta_final|params)"/g, '');
                content = content.trim();
                if (!content) continue;
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
                // Deep thinking event from bridge
                const thinkingData = parsed.data || {};
                const thinkingText =
                  thinkingData.reasoning ||
                  thinkingData.plan ||
                  JSON.stringify(thinkingData);
                thinkingContent += (thinkingContent ? "\n" : "") + thinkingText;
              } else if (parsed.type === "tool_start") {
                const toolName = parsed.data?.name || "unknown";
                const toolArgs = parsed.data?.arguments;
                toolCalls.push({
                  name: toolName,
                  arguments: toolArgs,
                  status: "loading",
                });
              } else if (parsed.type === "tool_result") {
                const toolName = parsed.data?.tool || "unknown";
                const toolResult = parsed.data?.result;
                // Find the matching loading tool call and update it
                const existingIdx = [...toolCalls]
                  .reverse()
                  .findIndex((t) => t.name === toolName && t.status === "loading");
                if (existingIdx >= 0) {
                  const realIdx = toolCalls.length - 1 - existingIdx;
                  toolCalls[realIdx] = {
                    ...toolCalls[realIdx],
                    result: typeof toolResult === "string" ? toolResult : JSON.stringify(toolResult),
                    status: "success",
                  };
                } else {
                  // No matching loading call, add as success
                  toolCalls.push({
                    name: toolName,
                    result: typeof toolResult === "string" ? toolResult : JSON.stringify(toolResult),
                    status: "success",
                  });
                }
              } else if (parsed.type === "meta") {
                // Metacognition event - could be displayed in thinking
                const metaData = parsed.data;
                if (metaData) {
                  thinkingContent += (thinkingContent ? "\n" : "") + `[Meta] ${JSON.stringify(metaData)}`;
                }
              } else if (parsed.type === "done") {
                // Agent finished
              } else if (parsed.type === "error") {
                // v5: Filter out raw JSON key names from error messages
                let errMsg = String(parsed.data || '');
                if (['"pensamiento"', '"accion"', '"respuesta_final"', '"params"'].some(k => errMsg.includes(k))) {
                  errMsg = 'Error procesando respuesta del modelo';
                }
                fullContent += `\nError: ${errMsg}`;
              }
            } else {
              // Direct Ollama format (no type field)
              let content = parsed.message?.content || "";
              tokenCount++;

              // v5: More robust filtering of internal agent JSON from direct Ollama responses
              const directTrimmed = content.trim();
              if (directTrimmed.startsWith('{')) {
                try {
                  const jsonObj = JSON.parse(directTrimmed);
                  // Extract useful content: respuesta_final > pensamiento
                  content = jsonObj.respuesta_final || jsonObj.pensamiento || '';
                  if (!content) continue;
                } catch {
                  // Partial JSON with internal keys - skip it
                  if (directTrimmed.includes('"pensamiento"') || directTrimmed.includes('"accion"') || directTrimmed.includes('"respuesta_final"')) {
                    continue;
                  }
                }
              }
              // Additional cleanup: remove residual JSON key fragments
              content = content.replace(/"(?:pensamiento|accion|respuesta_final|params)"/g, '');
              content = content.trim();
              if (!content) continue;

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
                for (const match of toolMatches) {
                  const toolName = match.slice(1, -1);
                  if (!toolCalls.find((t) => t.name === toolName)) {
                    toolCalls.push({
                      name: toolName,
                      status: "success",
                    });
                  }
                }
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
                  toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                  tokenCount,
                }
              : m
          )
        );
      }

      const responseTime = Date.now() - startTime;
      responseTimesRef.current.push(responseTime);

      // Mark any remaining loading tools as complete
      const finalToolCalls = toolCalls.map((t) =>
        t.status === "loading" ? { ...t, status: "success" as const } : t
      );

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                responseTime,
                isStreaming: false,
                toolCalls:
                  finalToolCalls.length > 0 ? finalToolCalls : undefined,
              }
            : m
        )
      );

      setSessionStats((prev) => ({
        messageCount: prev.messageCount + 1,
        toolsUsed: prev.toolsUsed + toolCalls.length,
        avgResponseTime:
          responseTimesRef.current.length > 0
            ? Math.round(
                responseTimesRef.current.reduce((a, b) => a + b, 0) /
                  responseTimesRef.current.length
              )
            : 0,
        totalTokens: prev.totalTokens + tokenCount,
      }));
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        // User cancelled - just mark streaming as done
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false } : m
          )
        );
      } else {
        const errMsg =
          error instanceof Error ? error.message : "Unknown error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: `Connection error: ${errMsg}`,
                  isStreaming: false,
                  responseTime: Date.now() - startTime,
                }
              : m
          )
        );
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
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

  const clearChat = async () => {
    setMessages([]);
    setSessionStats({
      messageCount: 0,
      toolsUsed: 0,
      avgResponseTime: 0,
      totalTokens: 0,
    });
    responseTimesRef.current = [];
    // Also clear agent memory via bridge (B2 fix)
    if (useAgent) {
      try {
        await fetch("/api/memory/clear", { method: "POST" });
      } catch {
        // Bridge not available - local clear is sufficient
      }
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div
      className="h-screen flex flex-col bg-[#000000] text-[#e0e0e0] overflow-hidden"
      style={{
        fontFamily:
          "var(--font-geist-mono), 'JetBrains Mono', 'Fira Code', ui-monospace, monospace",
      }}
    >
      {/* ─── Top Bar ─────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between h-9 px-4 border-b border-[rgba(255,255,255,0.06)] shrink-0 select-none">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 bg-[rgba(0,212,255,0.4)]" />
            <span className="text-[11px] tracking-[0.3em] text-[#e0e0e0] font-bold">
              AGENTLOCAL
            </span>
          </div>
          <span className="text-[10px] text-[#333333]">│</span>
          <span className="text-[11px] text-[#555555]">{selectedModel}</span>
          <div className="flex items-center gap-1.5 ml-1">
            <Circle
              size={5}
              className={
                status.connected
                  ? "fill-[#00ff88] text-[#00ff88]"
                  : "fill-[#ff3333] text-[#ff3333]"
              }
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
            title={
              useAgent
                ? "Full agent mode (ReAct + Tools + Persistent Memory)"
                : "Simple chat mode (no tools, no persistent memory)"
            }
            aria-label="Toggle agent mode"
          >
            {useAgent ? "AGENT" : "CHAT"}
          </button>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="text-[10px] text-[#555555] hover:text-[#777777] transition-colors px-2 py-0.5 border border-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.1)]"
              aria-label="Clear chat and memory"
              title={useAgent ? "Clear chat view and agent memory" : "Clear chat view"}
            >
              CLEAR
            </button>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 text-[#555555] hover:text-[#e0e0e0] transition-colors duration-150"
            aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            {sidebarOpen ? (
              <PanelRightClose size={14} />
            ) : (
              <PanelRightOpen size={14} />
            )}
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
              <WelcomeScreen
                status={status}
                selectedModel={selectedModel}
                useAgent={useAgent}
              />
            )}

            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                msg={msg}
                isLastAssistant={msg.id === lastAssistantId}
                isLoading={isLoading}
                expandedThinking={expandedThinking}
                toggleThinking={toggleThinking}
              />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* ─── Input Area ──────────────────────────────────────────────── */}
          {/* Bridge warning bar */}
          {useAgent && !status.agentAvailable && status.connected && (
            <div className="px-5 py-1.5 border-t border-[rgba(255,136,0,0.15)] bg-[rgba(255,136,0,0.03)] text-[10px] text-[#ff8800] flex items-center gap-2">
              <Circle
                size={4}
                className="fill-[#ff8800] text-[#ff8800]"
              />
              <span>
                Bridge not running — tools disabled. Start: python
                bridge_api.py
              </span>
            </div>
          )}

          {/* Uploaded files chips */}
          {uploadedFiles.length > 0 && (
            <div className="px-5 py-2 border-t border-[rgba(255,255,255,0.04)] flex flex-wrap gap-1.5">
              {uploadedFiles.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1.5 px-2 py-0.5 border border-[rgba(0,212,255,0.15)] bg-[rgba(0,212,255,0.03)] text-[10px] text-[#888]"
                >
                  <Paperclip size={9} className="text-[#555]" />
                  <span className="truncate max-w-[120px]">{file.name}</span>
                  <span className="text-[#444]">
                    ({formatBytes(file.size)})
                  </span>
                  <button
                    onClick={() => removeFile(i)}
                    className="text-[#555] hover:text-[#ff3333] transition-colors"
                  >
                    <X size={9} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="shrink-0 border-t border-[rgba(255,255,255,0.06)]">
            <div className="flex items-end gap-2 px-4 py-3">
              {/* Attach button */}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="pb-1 text-[#555555] hover:text-[rgba(0,212,255,0.6)] transition-colors duration-150 shrink-0"
                title="Attach file"
                aria-label="Attach file"
                disabled={!status.connected}
              >
                <Paperclip size={14} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFileSelect}
              />

              {/* Voice button */}
              <button
                onClick={toggleVoiceInput}
                className={`pb-1 transition-colors duration-150 shrink-0 ${
                  isRecording
                    ? "text-[#ff3333]"
                    : "text-[#555555] hover:text-[rgba(0,212,255,0.6)]"
                }`}
                title={
                  isRecording ? "Stop recording" : "Voice input"
                }
                aria-label={isRecording ? "Stop voice recording" : "Start voice input"}
                disabled={!status.connected}
              >
                {isRecording ? <MicOff size={14} /> : <Mic size={14} />}
              </button>

              {/* Input prompt symbol */}
              <div className="text-[12px] text-[#555555] pb-1 select-none shrink-0">
                {">"}
              </div>

              {/* Textarea */}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  status.connected ? "Enter message..." : "Ollama not connected"
                }
                disabled={!status.connected}
                rows={1}
                className="flex-1 bg-transparent text-[14px] text-[#e0e0e0] placeholder-[#3a3a3a] resize-none outline-none min-h-[22px] max-h-[140px] leading-[1.6] disabled:opacity-20"
                style={{ fontFamily: "inherit" }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = "auto";
                  target.style.height =
                    Math.min(target.scrollHeight, 120) + "px";
                }}
              />

              {/* Send / Stop button */}
              {isLoading ? (
                <button
                  onClick={stopGeneration}
                  className="pb-1 text-[#ff3333] hover:text-[#ff5555] transition-colors duration-150 shrink-0"
                  aria-label="Stop generation"
                  title="Stop generation"
                >
                  <Square size={14} />
                </button>
              ) : (
                <button
                  onClick={sendMessage}
                  disabled={!input.trim() || isLoading || !status.connected}
                  className="pb-1 text-[#555555] hover:text-[rgba(0,212,255,0.6)] disabled:opacity-10 disabled:hover:text-[#555555] transition-colors duration-150 shrink-0"
                  aria-label="Send message"
                >
                  <Send size={14} />
                </button>
              )}
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
            sidebarOpen ? "w-64" : "w-0"
          } ${
            isMobile
              ? "absolute right-0 top-0 bottom-0 z-20"
              : "relative"
          } shrink-0 border-l border-[rgba(255,255,255,0.06)] bg-[#050505] overflow-hidden transition-all duration-200`}
        >
          <div className="w-64 h-full overflow-y-auto px-4 py-4 space-y-5">
            {/* SYSTEM */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Server size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase">
                  System
                </h3>
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
                        <option
                          key={m.name}
                          value={m.name}
                          className="bg-[#111111] text-[#e0e0e0]"
                        >
                          {m.name}
                        </option>
                      ))
                    ) : (
                      <option
                        value={selectedModel}
                        className="bg-[#111111] text-[#e0e0e0]"
                      >
                        {selectedModel}
                      </option>
                    )}
                  </select>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">HOST</span>
                  <span className="text-[11px] text-[#666666]">
                    localhost:11434
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">STATUS</span>
                  <div className="flex items-center gap-1.5">
                    <Circle
                      size={4}
                      className={
                        status.connected
                          ? "fill-[#00ff88] text-[#00ff88]"
                          : "fill-[#ff3333] text-[#ff3333]"
                      }
                    />
                    <span className="text-[10px] text-[#555555]">
                      {status.connected ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">UPTIME</span>
                  <span className="text-[11px] text-[#666666] tabular-nums">
                    {formatUptime(uptime)}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#505050]">MODE</span>
                  <span
                    className={`text-[11px] ${
                      useAgent ? "text-[#00d4ff]" : "text-[#666666]"
                    }`}
                  >
                    {useAgent ? "AGENT" : "CHAT"}
                  </span>
                </div>
                {useAgent && status.agentAvailable !== undefined && (
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[#505050]">BRIDGE</span>
                    <div className="flex items-center gap-1.5">
                      <Circle
                        size={4}
                        className={
                          status.agentAvailable
                            ? "fill-[#00ff88] text-[#00ff88]"
                            : "fill-[#ff8800] text-[#ff8800]"
                        }
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
                <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">
                  Hardware
                </h3>
              </div>
              <HardwareStats />
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* SESSION */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Zap size={10} className="text-[#555555]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">
                  Session
                </h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <MessageSquare size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">MESSAGES</span>
                  </div>
                  <span className="text-[11px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.messageCount}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Wrench size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">TOOLS</span>
                  </div>
                  <span className="text-[11px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.toolsUsed}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Clock size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">AVG RESP</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.avgResponseTime > 0
                      ? `${sessionStats.avgResponseTime}ms`
                      : "—"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Activity size={9} className="text-[#505050]" />
                    <span className="text-[10px] text-[#505050]">TOKENS</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.totalTokens > 0
                      ? `~${sessionStats.totalTokens}`
                      : "—"}
                  </span>
                </div>
              </div>
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* MODELS */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <HardDrive size={10} className="text-[#555555]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">
                  Models
                </h3>
                {status.connected && (
                  <span className="text-[9px] text-[#505050] ml-auto">
                    {status.modelCount}
                  </span>
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
                        <span
                          className={`text-[11px] truncate mr-2 ${
                            model.name === selectedModel
                              ? "text-[#e0e0e0]"
                              : "text-[#666666]"
                          }`}
                        >
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
                    {status.connected
                      ? "No models found"
                      : "Cannot connect to Ollama"}
                  </div>
                )}
              </div>
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.05)]" />

            {/* TOOLS */}
            {tools.length > 0 && (
              <section>
                <div className="flex items-center gap-1.5 mb-3">
                  <Wrench size={10} className="text-[#555555]" />
                  <h3 className="text-[10px] tracking-[0.2em] text-[#555555] uppercase">
                    Tools
                  </h3>
                  <span className="text-[9px] text-[#505050] ml-auto">
                    {tools.length}
                  </span>
                </div>
                <div className="space-y-2 max-h-52 overflow-y-auto">
                  {Object.entries(toolsByCategory).map(
                    ([category, categoryTools]) => (
                      <div key={category}>
                        <div className="text-[9px] text-[#444444] tracking-[0.15em] uppercase mb-1">
                          {category}
                        </div>
                        <div className="space-y-0.5">
                          {categoryTools.map((tool) => (
                            <div
                              key={tool.name}
                              className="px-2 py-1 hover:bg-[rgba(255,255,255,0.02)] transition-colors"
                            >
                              <div className="text-[10px] text-[#888]">
                                {tool.name}
                              </div>
                              {tool.description && (
                                <div className="text-[9px] text-[#444] truncate">
                                  {tool.description}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  )}
                </div>
              </section>
            )}

            {/* Footer */}
            <div className="pt-6">
              <div className="text-[8px] text-[#333333] text-center tracking-[0.4em] uppercase">
                AgentLocal v1.0
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
