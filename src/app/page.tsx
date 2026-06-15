"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Toaster, toast } from "sonner";
import { useTheme } from "next-themes";
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
  Copy,
  Check,
  Plus,
  Trash2,
  FolderOpen,
  Settings,
  Sun,
  Moon,
  Search,
  Brain,
  Shield,
  Globe,
  Eye,
  WrenchIcon,
  Folder,
  File,
  FileCode,
  GitBranch,
  GitCommit,
  Terminal,
  ListTodo,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  Play,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";

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

interface BridgeConfig {
  model?: string;
  temperature?: number;
  max_tokens?: number;
  deep_thinking?: string;
  max_conversation_memory?: number;
  max_context_chars?: number;
  hybrid_search?: boolean;
  reranker?: boolean;
  allowed_directories?: string[];
  bridge_token_set?: boolean;
  [key: string]: unknown;
}

interface MemoryStats {
  total: number;
  short_term: number;
  medium_term: number;
  long_term: number;
}

interface MemoryEntryItem {
  id: string;
  type: string;
  category?: string | null;
  content: string;
  confidence: number;
  source?: string | null;
  createdAt: string;
}

interface ConversationListItem {
  id: string;
  title: string;
  model?: string | null;
  mode: string;
  createdAt: string;
  updatedAt: string;
  _count?: { messages: number };
}

type PanelMode = "chat" | "files" | "git" | "terminal" | "tasks";

interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number;
  modified?: string;
}

interface PendingConfirmation {
  toolName: string;
  arguments: Record<string, unknown>;
  resolve: (allowed: boolean) => void;
}

interface KanbanTask {
  id: string;
  title: string;
  status: string;
  description?: string;
  planId: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const MAX_CONVERSATION_MEMORY = 15;

const PROMPT_STARTERS = [
  { label: "Analyze a project", icon: "◆" },
  { label: "Search the web for...", icon: "◈" },
  { label: "Create a document", icon: "◇" },
  { label: "Run Python code", icon: "▶" },
  { label: "Explain a concept", icon: "○" },
  { label: "Manage my tasks", icon: "◎" },
];

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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return `${diffDays}d ago`;
  } else {
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }
}

function truncateTitle(title: string, maxLen: number = 22): string {
  if (title.length <= maxLen) return title;
  return title.slice(0, maxLen - 1) + "…";
}

// ─── Copy Button for Code Blocks ──────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-1 right-1 p-1 text-[#555] hover:text-[#e0e0e0] transition-colors"
      aria-label={copied ? "Copied" : "Copy code"}
      title={copied ? "Copied!" : "Copy code"}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
}

// ─── Tool Call Card Component ────────────────────────────────────────────────

function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
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

  const resultText = toolCall.result || "";
  const isTruncated = resultText.length > 500;
  const displayResult = expanded ? resultText : resultText.slice(0, 500);

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
        {resultText && (
          <button
            onClick={() => {
              navigator.clipboard.writeText(resultText).then(() => toast.success("Result copied"));
            }}
            className="ml-auto text-[#555] hover:text-[#e0e0e0] transition-colors"
            aria-label="Copy tool result"
            title="Copy result"
          >
            <Copy size={10} />
          </button>
        )}
      </div>
      {resultText && (
        <div className="mt-1.5 text-[11px] text-[#888] max-h-64 overflow-y-auto whitespace-pre-wrap border-l border-[rgba(255,255,255,0.06)] pl-2">
          {displayResult}
          {isTruncated && !expanded && (
            <button
              onClick={() => setExpanded(true)}
              className="text-[#00d4ff] hover:underline ml-1"
            >
              Show all ({resultText.length} chars)
            </button>
          )}
          {expanded && isTruncated && (
            <button
              onClick={() => setExpanded(false)}
              className="text-[#555] hover:underline ml-1"
            >
              Collapse
            </button>
          )}
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
    const interval = setInterval(fetchSystem, 5000);
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
  // D15: Copy button state for full assistant message
  const [msgCopied, setMsgCopied] = useState(false);

  const copyFullMessage = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setMsgCopied(true);
      setTimeout(() => setMsgCopied(false), 2000);
      toast.success("Message copied");
    } catch {
      // Clipboard not available
    }
  };

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
    <div className="animate-fade-in group relative">
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
                      <div className="relative">
                        <CopyButton text={String(children).replace(/\n$/, "")} />
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match[1]}
                          PreTag="div"
                          className="!bg-[rgba(255,255,255,0.04)] !border !border-[rgba(255,255,255,0.06)] !rounded-sm !my-2 !text-[12px]"
                        >
                          {String(children).replace(/\n$/, "")}
                        </SyntaxHighlighter>
                      </div>
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

          {/* Copy full message button - D15 fix */}
          {!isStreaming && msg.content && (
            <button
              onClick={copyFullMessage}
              className="absolute top-1 right-1 p-1 text-[#555] hover:text-[#e0e0e0] transition-colors opacity-0 group-hover:opacity-100"
              aria-label={msgCopied ? "Copied" : "Copy message"}
              title={msgCopied ? "Copied!" : "Copy message"}
            >
              {msgCopied ? <Check size={12} /> : <Copy size={12} />}
            </button>
          )}

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
  onStarterClick,
}: {
  status: SystemStatus;
  selectedModel: string;
  useAgent: boolean;
  onStarterClick: (prompt: string) => void;
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

      {/* Prompt Starters */}
      {status.connected && (
        <div className="mt-4 w-full max-w-md">
          <div className="text-[9px] text-[#3a3a3a] tracking-[0.2em] uppercase mb-2.5 text-center">
            Quick Prompts
          </div>
          <div className="grid grid-cols-2 gap-2">
            {PROMPT_STARTERS.map((starter) => (
              <button
                key={starter.label}
                onClick={() => onStarterClick(starter.label)}
                className="flex items-center gap-2 px-3 py-2 border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.015)] hover:border-[rgba(0,212,255,0.2)] hover:bg-[rgba(0,212,255,0.03)] text-[11px] text-[#666666] hover:text-[#aaa] transition-all duration-150 text-left group"
              >
                <span className="text-[rgba(0,212,255,0.3)] group-hover:text-[rgba(0,212,255,0.6)] text-[10px] shrink-0">
                  {starter.icon}
                </span>
                <span className="truncate">{starter.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Theme Toggle Button ─────────────────────────────────────────────────────

function ThemeToggleButton() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <button className="p-1.5 text-[var(--zai-text-dim)]" aria-label="Toggle theme">
        <Moon size={14} />
      </button>
    );
  }

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="p-1.5 text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] transition-colors duration-150"
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
    >
      {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  );
}

// ─── Settings Dialog Component ────────────────────────────────────────────────

function SettingsDialog({
  open,
  onOpenChange,
  selectedModel,
  bridgeConfig,
  onSaveConfig,
  userLanguage,
  setUserLanguage,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedModel: string;
  bridgeConfig: BridgeConfig | null;
  onSaveConfig: (key: string, value: string | number | boolean, category?: string) => void;
  userLanguage: string;
  setUserLanguage: (lang: string) => void;
}) {
  const { theme, setTheme } = useTheme();
  const [localConfig, setLocalConfig] = useState<BridgeConfig>({});
  const [language, setLanguage] = useState(userLanguage.toUpperCase() === "ES" ? "ES" : "EN");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (bridgeConfig) setLocalConfig({ ...bridgeConfig });
  }, [bridgeConfig]);

  const updateLocal = (key: string, value: unknown) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
  };

  const saveAndNotify = (key: string, value: unknown, category?: string) => {
    onSaveConfig(key, String(value), category);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px] bg-[var(--zai-bg-subtle)] border-[var(--zai-border)] text-[var(--zai-text)] max-h-[85vh] overflow-y-auto" style={{ fontFamily: "inherit" }}>
        <DialogHeader>
          <DialogTitle className="text-[13px] tracking-[0.15em] text-[var(--zai-text)]">
            SETTINGS
          </DialogTitle>
          <DialogDescription className="text-[11px] text-[var(--zai-text-dim)]">
            Configure agent model, memory, security, and UI preferences.
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="model" className="mt-2">
          <TabsList className="bg-[var(--zai-bg-elevated)] h-8 p-0.5 w-full">
            <TabsTrigger value="model" className="text-[10px] tracking-wider flex-1 h-7 data-[state=active]:bg-[var(--zai-accent-dim)] data-[state=active]:text-[var(--zai-accent)]">
              MODEL
            </TabsTrigger>
            <TabsTrigger value="memory" className="text-[10px] tracking-wider flex-1 h-7 data-[state=active]:bg-[var(--zai-accent-dim)] data-[state=active]:text-[var(--zai-accent)]">
              MEMORY
            </TabsTrigger>
            <TabsTrigger value="security" className="text-[10px] tracking-wider flex-1 h-7 data-[state=active]:bg-[var(--zai-accent-dim)] data-[state=active]:text-[var(--zai-accent)]">
              SECURITY
            </TabsTrigger>
            <TabsTrigger value="ui" className="text-[10px] tracking-wider flex-1 h-7 data-[state=active]:bg-[var(--zai-accent-dim)] data-[state=active]:text-[var(--zai-accent)]">
              UI
            </TabsTrigger>
          </TabsList>

          {/* ─── Model Tab ─────────────────────────────────────────────── */}
          <TabsContent value="model" className="mt-4 space-y-4">
            <div className="space-y-2">
              <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">CURRENT MODEL</Label>
              <div className="px-3 py-2 border border-[var(--zai-border)] bg-[var(--zai-bg)] text-[11px] text-[var(--zai-text)]">
                {selectedModel || "No model selected"}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">TEMPERATURE</Label>
                <span className="text-[11px] text-[var(--zai-accent)] tabular-nums">
                  {Number(localConfig.temperature ?? 0.7).toFixed(2)}
                </span>
              </div>
              <Slider
                value={[Number(localConfig.temperature ?? 0.7)]}
                min={0}
                max={2}
                step={0.05}
                onValueChange={([v]) => updateLocal("temperature", v)}
                onValueCommit={([v]) => saveAndNotify("temperature", v, "model")}
                className="py-2"
              />
              <div className="flex justify-between text-[9px] text-[var(--zai-text-dim)]">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">MAX TOKENS</Label>
                <span className="text-[11px] text-[var(--zai-accent)] tabular-nums">
                  {localConfig.max_tokens ?? 4096}
                </span>
              </div>
              <Slider
                value={[Number(localConfig.max_tokens ?? 4096)]}
                min={256}
                max={32768}
                step={256}
                onValueChange={([v]) => updateLocal("max_tokens", v)}
                onValueCommit={([v]) => saveAndNotify("max_tokens", v, "model")}
                className="py-2"
              />
              <div className="flex justify-between text-[9px] text-[var(--zai-text-dim)]">
                <span>256</span>
                <span>32K</span>
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">DEEP THINKING MODE</Label>
              <Select
                value={String(localConfig.deep_thinking ?? "off")}
                onValueChange={(v) => { updateLocal("deep_thinking", v); saveAndNotify("deep_thinking", v, "model"); }}
              >
                <SelectTrigger className="h-8 text-[11px] bg-[var(--zai-bg)] border-[var(--zai-border)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--zai-bg-subtle)] border-[var(--zai-border)]">
                  <SelectItem value="off" className="text-[11px]">Off — No thinking</SelectItem>
                  <SelectItem value="native" className="text-[11px]">Native — Model&apos;s built-in</SelectItem>
                  <SelectItem value="cot" className="text-[11px]">CoT — Chain of Thought</SelectItem>
                  <SelectItem value="reflection" className="text-[11px]">Reflection — Self-correct</SelectItem>
                  <SelectItem value="full" className="text-[11px]">Full — All strategies</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </TabsContent>

          {/* ─── Memory Tab ─────────────────────────────────────────────── */}
          <TabsContent value="memory" className="mt-4 space-y-4">
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">MAX CONVERSATION MEMORY</Label>
                <span className="text-[11px] text-[var(--zai-accent)] tabular-nums">
                  {localConfig.max_conversation_memory ?? 15}
                </span>
              </div>
              <Slider
                value={[Number(localConfig.max_conversation_memory ?? 15)]}
                min={5}
                max={50}
                step={1}
                onValueChange={([v]) => updateLocal("max_conversation_memory", v)}
                onValueCommit={([v]) => saveAndNotify("max_conversation_memory", v, "memory")}
                className="py-2"
              />
              <div className="flex justify-between text-[9px] text-[var(--zai-text-dim)]">
                <span>5 msgs</span>
                <span>50 msgs</span>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">MAX CONTEXT CHARS</Label>
                <span className="text-[11px] text-[var(--zai-accent)] tabular-nums">
                  {(localConfig.max_context_chars ?? 8000).toLocaleString()}
                </span>
              </div>
              <Slider
                value={[Number(localConfig.max_context_chars ?? 8000)]}
                min={2000}
                max={50000}
                step={500}
                onValueChange={([v]) => updateLocal("max_context_chars", v)}
                onValueCommit={([v]) => saveAndNotify("max_context_chars", v, "memory")}
                className="py-2"
              />
              <div className="flex justify-between text-[9px] text-[var(--zai-text-dim)]">
                <span>2K</span>
                <span>50K</span>
              </div>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">HYBRID SEARCH</Label>
                <p className="text-[9px] text-[var(--zai-text-dim)] mt-0.5">Combine semantic + keyword search</p>
              </div>
              <Switch
                checked={Boolean(localConfig.hybrid_search ?? true)}
                onCheckedChange={(v) => { updateLocal("hybrid_search", v); saveAndNotify("hybrid_search", v, "memory"); }}
              />
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">RERANKER</Label>
                <p className="text-[9px] text-[var(--zai-text-dim)] mt-0.5">Re-rank search results for relevance</p>
              </div>
              <Switch
                checked={Boolean(localConfig.reranker ?? false)}
                onCheckedChange={(v) => { updateLocal("reranker", v); saveAndNotify("reranker", v, "memory"); }}
              />
            </div>
          </TabsContent>

          {/* ─── Security Tab ─────────────────────────────────────────────── */}
          <TabsContent value="security" className="mt-4 space-y-4">
            <div className="space-y-2">
              <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">ALLOWED DIRECTORIES</Label>
              {bridgeConfig?.allowed_directories && bridgeConfig.allowed_directories.length > 0 ? (
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {bridgeConfig.allowed_directories.map((dir, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-1.5 border border-[var(--zai-border)] bg-[var(--zai-bg)] text-[10px] text-[var(--zai-text)]">
                      <FolderOpen size={10} className="text-[var(--zai-accent)] shrink-0" />
                      <span className="truncate">{dir}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="px-3 py-2 border border-[var(--zai-border)] bg-[var(--zai-bg)] text-[10px] text-[var(--zai-text-dim)]">
                  No directories configured (all accessible)
                </div>
              )}
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">BRIDGE TOKEN</Label>
                <p className="text-[9px] text-[var(--zai-text-dim)] mt-0.5">Authentication for bridge API</p>
              </div>
              <div className="flex items-center gap-2">
                <Circle
                  size={6}
                  className={
                    bridgeConfig?.bridge_token_set
                      ? "fill-[var(--zai-green)] text-[var(--zai-green)]"
                      : "fill-[var(--zai-red)] text-[var(--zai-red)]"
                  }
                />
                <span className="text-[10px] text-[var(--zai-text-dim)]">
                  {bridgeConfig?.bridge_token_set ? "Configured" : "Not set"}
                </span>
              </div>
            </div>
          </TabsContent>

          {/* ─── UI Tab ─────────────────────────────────────────────────────── */}
          <TabsContent value="ui" className="mt-4 space-y-4">
            <div className="flex items-center justify-between py-2">
              <div>
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">THEME</Label>
                <p className="text-[9px] text-[var(--zai-text-dim)] mt-0.5">
                  {theme === "dark" ? "Dark terminal aesthetic" : "Light mode for daytime"}
                </p>
              </div>
              <button
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="flex items-center gap-2 px-3 py-1.5 border border-[var(--zai-border)] bg-[var(--zai-bg)] hover:bg-[var(--zai-bg-elevated)] text-[10px] text-[var(--zai-text)] transition-colors"
              >
                {theme === "dark" ? (
                  <>
                    <Sun size={12} className="text-[var(--zai-accent)]" />
                    <span>LIGHT</span>
                  </>
                ) : (
                  <>
                    <Moon size={12} className="text-[var(--zai-accent)]" />
                    <span>DARK</span>
                  </>
                )}
              </button>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <Label className="text-[10px] tracking-wider text-[var(--zai-text-dim)]">LANGUAGE</Label>
                <p className="text-[9px] text-[var(--zai-text-dim)] mt-0.5">Interface language</p>
              </div>
              <Select
                value={language}
                onValueChange={(v) => {
                  setLanguage(v);
                  // D5 fix: Persist language choice to localStorage
                  const langCode = v.toLowerCase();
                  localStorage.setItem("agentlocal-language", langCode);
                  setUserLanguage(langCode);
                }}
              >
                <SelectTrigger className="h-7 text-[10px] w-24 bg-[var(--zai-bg)] border-[var(--zai-border)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--zai-bg-subtle)] border-[var(--zai-border)]">
                  <SelectItem value="ES" className="text-[10px]">Español</SelectItem>
                  <SelectItem value="EN" className="text-[10px]">English</SelectItem>
                </SelectContent>
              </Select>
              {/* D14 fix: Mark i18n as coming soon */}
              <span className="text-[8px] text-[var(--zai-text-dim)] italic">UI translation coming soon</span>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

// ─── Memory Viewer Dialog Component ─────────────────────────────────────────

function MemoryViewerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [entries, setEntries] = useState<MemoryEntryItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");
  const [expandedEntry, setExpandedEntry] = useState<string | null>(null);

  const memoryTypes = ["all", "short_term", "long_term", "working", "episodic", "preference"];

  useEffect(() => {
    if (open) {
      setLoading(true);
      const typeParam = filterType !== "all" ? `&type=${filterType}` : "";
      fetch(`/api/memory?limit=100${searchQuery ? `&keyword=${encodeURIComponent(searchQuery)}` : ""}${typeParam}`)
        .then((res) => res.ok ? res.json() : { entries: [] })
        .then((data) => setEntries(data.entries || []))
        .catch(() => setEntries([]))
        .finally(() => setLoading(false));
    }
  }, [open, searchQuery, filterType]);

  const deleteEntry = async (id: string) => {
    try {
      const res = await fetch(`/api/memory?id=${id}`, { method: "DELETE" });
      if (res.ok) {
        setEntries((prev) => prev.filter((e) => e.id !== id));
        toast.success("Memory entry deleted");
      }
    } catch {
      toast.error("Failed to delete entry");
    }
  };

  const typeColor: Record<string, string> = {
    short_term: "text-[#00d4ff] border-[rgba(0,212,255,0.3)]",
    long_term: "text-[#ffd93d] border-[rgba(255,217,61,0.3)]",
    working: "text-[#00ff88] border-[rgba(0,255,136,0.3)]",
    episodic: "text-[#a855f7] border-[rgba(168,85,247,0.3)]",
    preference: "text-[#ff8800] border-[rgba(255,136,0,0.3)]",
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] bg-[var(--zai-bg-subtle)] border-[var(--zai-border)] text-[var(--zai-text)] max-h-[85vh] flex flex-col" style={{ fontFamily: "inherit" }}>
        <DialogHeader>
          <DialogTitle className="text-[13px] tracking-[0.15em] text-[var(--zai-text)]">
            MEMORY ENTRIES
          </DialogTitle>
          <DialogDescription className="text-[11px] text-[var(--zai-text-dim)]">
            {entries.length} entries stored in agent memory
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2 mt-2">
          <div className="relative flex-1">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--zai-text-dim)]" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memory..."
              className="pl-8 h-8 text-[11px] bg-[var(--zai-bg)] border-[var(--zai-border)] text-[var(--zai-text)] placeholder:text-[var(--zai-text-dim)]"
              style={{ fontFamily: "inherit" }}
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="h-8 px-2 text-[10px] bg-[var(--zai-bg)] border border-[var(--zai-border)] text-[var(--zai-text)] outline-none cursor-pointer"
            style={{ fontFamily: "inherit" }}
            aria-label="Filter by memory type"
          >
            {memoryTypes.map((t) => (
              <option key={t} value={t} className="bg-[var(--zai-bg-subtle)]">
                {t === "all" ? "All Types" : t.replace("_", " ").toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 overflow-y-auto mt-3 space-y-1.5 min-h-0 max-h-[50vh]">
          {loading ? (
            <div className="text-[10px] text-[var(--zai-text-dim)] text-center py-4">Loading...</div>
          ) : entries.length === 0 ? (
            <div className="text-[10px] text-[var(--zai-text-dim)] text-center py-4">
              {searchQuery ? "No entries match your search" : "No memory entries found"}
            </div>
          ) : (
            entries.map((entry) => (
              <div
                key={entry.id}
                className="px-3 py-2 border border-[var(--zai-border)] bg-[var(--zai-bg)] hover:border-[var(--zai-border-accent)] transition-colors group"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Badge
                    variant="outline"
                    className={`text-[8px] px-1.5 py-0 h-4 ${typeColor[entry.type] || "border-[var(--zai-border)] text-[var(--zai-text-dim)]"}`}
                  >
                    {entry.type.replace("_", " ").toUpperCase()}
                  </Badge>
                  {entry.category && (
                    <span className="text-[8px] text-[var(--zai-text-dim)]">{entry.category}</span>
                  )}
                  <span className="text-[8px] text-[var(--zai-text-dim)] ml-auto">
                    {Math.round(entry.confidence * 100)}%
                  </span>
                  <button
                    onClick={() => setExpandedEntry(expandedEntry === entry.id ? null : entry.id)}
                    className="text-[8px] text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] transition-colors"
                    aria-label={expandedEntry === entry.id ? "Collapse entry" : "Expand entry"}
                  >
                    {expandedEntry === entry.id ? "▲" : "▼"}
                  </button>
                  <button
                    onClick={() => deleteEntry(entry.id)}
                    className="text-[8px] text-[var(--zai-text-dim)] hover:text-[var(--zai-red)] transition-colors opacity-0 group-hover:opacity-100"
                    aria-label="Delete memory entry"
                  >
                    <Trash2 size={9} />
                  </button>
                </div>
                <div className={`text-[10px] text-[var(--zai-text)] leading-[1.5] ${expandedEntry === entry.id ? "" : "line-clamp-2"}`}>
                  {entry.content}
                </div>
                {expandedEntry === entry.id && entry.context && (
                  <div className="text-[9px] text-[var(--zai-text-dim)] mt-1 border-t border-[var(--zai-border)] pt-1">
                    <span className="font-bold">Context:</span> {entry.context}
                  </div>
                )}
                {expandedEntry === entry.id && entry.tags && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {JSON.parse(entry.tags || "[]").map((tag: string, i: number) => (
                      <span key={i} className="text-[8px] px-1 py-0.5 bg-[var(--zai-bg-elevated)] text-[var(--zai-text-dim)]">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                <div className="text-[8px] text-[var(--zai-text-dim)] mt-1">
                  {entry.source && <span>{entry.source} · </span>}
                  {formatDate(entry.createdAt)}
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── File Explorer Panel ─────────────────────────────────────────────────────

function FileExplorerPanel({ onExecuteTool }: { onExecuteTool: (toolName: string, args: Record<string, unknown>, skipConfirm?: boolean) => Promise<string> }) {
  const [rootPath, setRootPath] = useState(".");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dirCache, setDirCache] = useState<Record<string, FileEntry[]>>({});
  const [breadcrumb, setBreadcrumb] = useState<string[]>(["."]);

  const fetchDir = useCallback(async (dirPath: string) => {
    try {
      const result = await onExecuteTool("listar_archivos", { ruta: dirPath }, true);
      const parsed = JSON.parse(result);
      const entries: FileEntry[] = Array.isArray(parsed) ? parsed : parsed.archivos || parsed.files || parsed.entries || [];
      return entries.map((e: any) => ({
        name: e.name || e.nombre || e,
        path: e.path || e.ruta || (dirPath === "." ? e.name || e.nombre || e : `${dirPath}/${e.name || e.nombre || e}`),
        is_dir: e.is_dir ?? e.isDirectory ?? e.es_directorio ?? false,
        size: e.size ?? e.tamano,
        modified: e.modified ?? e.modificado,
      })).sort((a: FileEntry, b: FileEntry) => {
        if (a.is_dir && !b.is_dir) return -1;
        if (!a.is_dir && b.is_dir) return 1;
        return a.name.localeCompare(b.name);
      });
    } catch {
      return null;
    }
  }, [onExecuteTool]);

  const loadRoot = useCallback(async () => {
    setLoading(true);
    const entries = await fetchDir(rootPath);
    if (entries) {
      setFiles(entries);
      setDirCache((prev) => ({ ...prev, [rootPath]: entries }));
    }
    setLoading(false);
  }, [rootPath, fetchDir]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadRoot();
  }, [loadRoot]);

  const toggleDir = async (dirPath: string) => {
    const newExpanded = new Set(expandedDirs);
    if (newExpanded.has(dirPath)) {
      newExpanded.delete(dirPath);
    } else {
      newExpanded.add(dirPath);
      if (!dirCache[dirPath]) {
        const entries = await fetchDir(dirPath);
        if (entries) {
          setDirCache((prev) => ({ ...prev, [dirPath]: entries }));
        }
      }
    }
    setExpandedDirs(newExpanded);
  };

  const openFile = async (filePath: string) => {
    setPreviewPath(filePath);
    setPreviewContent("Loading...");
    try {
      const result = await onExecuteTool("leer_archivo", { ruta: filePath }, true);
      setPreviewContent(result);
    } catch (err) {
      setPreviewContent(`Error loading file: ${err}`);
    }
  };

  const navigateTo = (index: number) => {
    if (index === -1) {
      setRootPath(".");
      setBreadcrumb(["."]);
    } else {
      const newPath = breadcrumb.slice(0, index + 1).join("/");
      setRootPath(newPath === "." ? "." : newPath);
      setBreadcrumb(breadcrumb.slice(0, index + 1));
    }
    setExpandedDirs(new Set());
    setDirCache({});
    setPreviewContent(null);
    setPreviewPath(null);
  };

  const openDirAsRoot = (dirPath: string) => {
    setRootPath(dirPath);
    const parts = dirPath.split("/").filter(Boolean);
    setBreadcrumb(dirPath === "." ? ["."] : parts);
    setExpandedDirs(new Set());
    setDirCache({});
    setPreviewContent(null);
    setPreviewPath(null);
  };

  const renderTree = (entries: FileEntry[], depth: number = 0) => {
    return entries.map((entry) => {
      const isExpanded = expandedDirs.has(entry.path);
      const indent = depth * 16;
      return (
        <div key={entry.path}>
          <div
            className={`flex items-center gap-1.5 px-2 py-1 hover:bg-[rgba(255,255,255,0.03)] cursor-pointer transition-colors ${
              previewPath === entry.path ? "bg-[rgba(0,212,255,0.06)] border-l border-[rgba(0,212,255,0.3)]" : ""
            }`}
            style={{ paddingLeft: `${8 + indent}px` }}
            onClick={() => {
              if (entry.is_dir) {
                toggleDir(entry.path);
              } else {
                openFile(entry.path);
              }
            }}
            onDoubleClick={() => {
              if (entry.is_dir) {
                openDirAsRoot(entry.path);
              }
            }}
          >
            {entry.is_dir ? (
              <>
                {isExpanded ? (
                  <ChevronDown size={11} className="text-[#666] shrink-0" />
                ) : (
                  <ChevronRight size={11} className="text-[#666] shrink-0" />
                )}
                <Folder size={12} className="text-[#ffd93d] shrink-0" />
              </>
            ) : (
              <>
                <span className="w-[11px] shrink-0" />
                {entry.name.endsWith(".ts") || entry.name.endsWith(".tsx") || entry.name.endsWith(".js") || entry.name.endsWith(".py") ? (
                  <FileCode size={12} className="text-[#00d4ff] shrink-0" />
                ) : (
                  <File size={12} className="text-[#888] shrink-0" />
                )}
              </>
            )}
            <span className="text-[11px] text-[#ccc] truncate">{entry.name}</span>
            {!entry.is_dir && entry.size !== undefined && (
              <span className="text-[9px] text-[#555] ml-auto shrink-0">{formatBytes(entry.size)}</span>
            )}
          </div>
          {entry.is_dir && isExpanded && dirCache[entry.path] && (
            <div>{renderTree(dirCache[entry.path], depth + 1)}</div>
          )}
        </div>
      );
    });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--zai-border)]">
        <FolderOpen size={13} className="text-[var(--zai-accent)]" />
        <span className="text-[11px] tracking-[0.15em] text-[var(--zai-text)] uppercase font-bold">FILES</span>
        <div className="flex-1" />
        <button onClick={loadRoot} className="p-1 text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] transition-colors" title="Refresh" aria-label="Refresh file explorer">
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1 px-4 py-1.5 border-b border-[rgba(255,255,255,0.04)] overflow-x-auto">
        {breadcrumb.map((part, i) => (
          <div key={i} className="flex items-center gap-1 shrink-0">
            {i > 0 && <ChevronRight size={9} className="text-[#444]" />}
            <button
              onClick={() => navigateTo(i)}
              className={`text-[10px] hover:text-[var(--zai-accent)] transition-colors ${
                i === breadcrumb.length - 1 ? "text-[var(--zai-text)]" : "text-[var(--zai-text-dim)]"
              }`}
            >
              {part}
            </button>
          </div>
        ))}
      </div>

      {/* Content */}
      <div className="flex flex-1 min-h-0">
        {/* Tree */}
        <div className="flex-1 overflow-y-auto min-w-0 border-r border-[rgba(255,255,255,0.04)]">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <span className="text-[11px] text-[var(--zai-text-dim)] animate-pulse">Loading files...</span>
            </div>
          ) : files.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <span className="text-[11px] text-[var(--zai-text-dim)]">No files found</span>
            </div>
          ) : (
            <div className="py-1">{renderTree(files)}</div>
          )}
        </div>

        {/* Preview */}
        {previewContent !== null && (
          <div className="w-1/2 flex flex-col min-w-0">
            <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[rgba(255,255,255,0.04)]">
              <FileCode size={10} className="text-[var(--zai-accent)]" />
              <span className="text-[10px] text-[var(--zai-text-dim)] truncate">{previewPath}</span>
              <button onClick={() => { setPreviewContent(null); setPreviewPath(null); }} className="ml-auto text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] transition-colors">
                <X size={10} />
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-3 text-[11px] text-[#aaa] leading-[1.6] whitespace-pre-wrap font-mono">
              {previewContent}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Git Panel ───────────────────────────────────────────────────────────────

function GitPanel({ onExecuteTool }: { onExecuteTool: (toolName: string, args: Record<string, unknown>, skipConfirm?: boolean) => Promise<string> }) {
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [activeOp, setActiveOp] = useState<string | null>(null);
  const [branch, setBranch] = useState<string>("");
  const [statusCounts, setStatusCounts] = useState({ modified: 0, staged: 0, untracked: 0 });

  const runGitOp = async (operation: string, args?: Record<string, unknown>) => {
    setLoading(true);
    setActiveOp(operation);
    setOutput((prev) => prev + `\n$ git ${operation}\n`);
    try {
      const result = await onExecuteTool("git_operacion", { operacion: operation, ...args });
      const parsed = JSON.parse(result);
      const text = typeof parsed === "string" ? parsed : parsed.output || parsed.result || parsed.message || JSON.stringify(parsed, null, 2);
      setOutput((prev) => prev + text + "\n");

      // Parse status info
      if (operation === "status") {
        const statusText = typeof parsed === "string" ? parsed : JSON.stringify(parsed);
        const modified = (statusText.match(/modified/gi) || []).length;
        const staged = (statusText.match(/new file/gi) || []).length;
        const untracked = (statusText.match(/untracked/gi) || []).length;
        setStatusCounts({ modified, staged, untracked });
      }
      if (operation === "branch" || operation === "status") {
        const branchMatch = text.match(/On branch (\S+)/);
        if (branchMatch) setBranch(branchMatch[1]);
        const branchStarMatch = text.match(/\* (\S+)/);
        if (branchStarMatch && !branchMatch) setBranch(branchStarMatch[1]);
      }
    } catch (err) {
      setOutput((prev) => prev + `Error: ${err}\n`);
    }
    setLoading(false);
    setActiveOp(null);
  };

  const clearOutput = () => setOutput("");

  useEffect(() => {
    runGitOp("status");
  }, []);

  const gitButtons = [
    { op: "status", label: "STATUS", icon: <Eye size={11} /> },
    { op: "log", label: "LOG", icon: <GitCommit size={11} /> },
    { op: "diff", label: "DIFF", icon: <FileCode size={11} /> },
    { op: "branch", label: "BRANCH", icon: <GitBranch size={11} /> },
    { op: "add .", label: "ADD ALL", icon: <Plus size={11} /> },
    { op: "pull", label: "PULL", icon: <ArrowDown size={11} /> },
    { op: "push", label: "PUSH", icon: <ArrowUp size={11} /> },
  ];

  const commitChanges = async () => {
    const message = prompt("Commit message:");
    if (!message) return;
    await runGitOp("add", { ruta: "." });
    await runGitOp("commit", { mensaje: message });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--zai-border)]">
        <GitBranch size={13} className="text-[var(--zai-accent)]" />
        <span className="text-[11px] tracking-[0.15em] text-[var(--zai-text)] uppercase font-bold">GIT</span>
        {branch && (
          <>
            <span className="text-[10px] text-[#444]">│</span>
            <span className="text-[10px] text-[var(--zai-accent)]">{branch}</span>
          </>
        )}
        <div className="flex-1" />
        {statusCounts.modified > 0 && <Badge variant="outline" className="text-[8px] px-1.5 h-4 border-[#ffd93d] text-[#ffd93d]">{statusCounts.modified}M</Badge>}
        {statusCounts.staged > 0 && <Badge variant="outline" className="text-[8px] px-1.5 h-4 border-[#00ff88] text-[#00ff88]">{statusCounts.staged}S</Badge>}
        {statusCounts.untracked > 0 && <Badge variant="outline" className="text-[8px] px-1.5 h-4 border-[#888] text-[#888]">{statusCounts.untracked}U</Badge>}
        <button onClick={clearOutput} className="p-1 text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] transition-colors" title="Clear output" aria-label="Clear output">
          <Trash2 size={11} />
        </button>
        <button onClick={commitChanges} className="flex items-center gap-1 px-2 py-0.5 border border-[var(--zai-border-accent)] text-[9px] text-[var(--zai-accent)] hover:bg-[var(--zai-accent-dim)] transition-colors tracking-wider" title="Stage all and commit" aria-label="Stage all and commit">
          <GitCommit size={9} />
          COMMIT
        </button>
      </div>

      {/* Buttons */}
      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-[rgba(255,255,255,0.04)] overflow-x-auto">
        {gitButtons.map((btn) => (
          <button
            key={btn.op}
            onClick={() => runGitOp(btn.op)}
            disabled={loading}
            className={`flex items-center gap-1.5 px-2.5 py-1 border text-[9px] tracking-wider transition-colors shrink-0 ${
              activeOp === btn.op
                ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[var(--zai-accent)]"
                : "border-[var(--zai-border)] text-[var(--zai-text-dim)] hover:border-[var(--zai-border)] hover:text-[var(--zai-text)] hover:bg-[rgba(255,255,255,0.03)]"
            } disabled:opacity-30`}
          >
            {btn.icon}
            {btn.label}
          </button>
        ))}
      </div>

      {/* Output */}
      <div className="flex-1 overflow-auto p-4">
        <pre className="text-[11px] text-[#aaa] leading-[1.6] whitespace-pre-wrap font-mono">{output || "Run a git command to see output..."}</pre>
        {loading && (
          <span className="inline-block w-[7px] h-[14px] bg-[rgba(0,212,255,0.5)] cursor-blink" />
        )}
      </div>
    </div>
  );
}

// ─── Terminal Panel ──────────────────────────────────────────────────────────

function TerminalPanel({ onExecuteTool }: { onExecuteTool: (toolName: string, args: Record<string, unknown>, skipConfirm?: boolean) => Promise<string> }) {
  const [cmdInput, setCmdInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [output, setOutput] = useState<string[]>(["$ Terminal ready. Type a command and press Enter."]);
  const [loading, setLoading] = useState(false);
  const outputEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    outputEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [output]);

  const executeCommand = async () => {
    const cmd = cmdInput.trim();
    if (!cmd || loading) return;

    setHistory((prev) => [...prev, cmd]);
    setHistoryIndex(-1);
    setCmdInput("");
    setOutput((prev) => [...prev, `$ ${cmd}`]);
    setLoading(true);

    try {
      const result = await onExecuteTool("ejecutar_bash", { comando: cmd });
      const parsed = JSON.parse(result);
      const text = typeof parsed === "string" ? parsed : parsed.output || parsed.result || parsed.stdout || JSON.stringify(parsed, null, 2);
      const lines = text.split("\n");
      setOutput((prev) => [...prev, ...lines]);
    } catch (err) {
      setOutput((prev) => [...prev, `Error: ${err}`]);
    }
    setLoading(false);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      executeCommand();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = historyIndex === -1 ? history.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(newIndex);
        setCmdInput(history[newIndex]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex >= 0) {
        const newIndex = historyIndex + 1;
        if (newIndex >= history.length) {
          setHistoryIndex(-1);
          setCmdInput("");
        } else {
          setHistoryIndex(newIndex);
          setCmdInput(history[newIndex]);
        }
      }
    }
  };

  const clearOutput = () => {
    setOutput(["$ Terminal cleared."]);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--zai-border)]">
        <Terminal size={13} className="text-[var(--zai-accent)]" />
        <span className="text-[11px] tracking-[0.15em] text-[var(--zai-text)] uppercase font-bold">TERMINAL</span>
        <div className="flex-1" />
        <button onClick={clearOutput} className="p-1 text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] transition-colors" title="Clear terminal" aria-label="Clear terminal">
          <Trash2 size={11} />
        </button>
      </div>

      {/* Output */}
      <div className="flex-1 overflow-auto p-4 space-y-0">
        {output.map((line, i) => (
          <div key={i} className={`text-[11px] leading-[1.6] font-mono whitespace-pre-wrap ${
            line.startsWith("$") ? "text-[#00d4ff]" :
            line.startsWith("Error") ? "text-[#ff3333]" :
            "text-[#aaa]"
          }`}>
            {line}
          </div>
        ))}
        {loading && (
          <span className="inline-block w-[7px] h-[14px] bg-[rgba(0,212,255,0.5)] cursor-blink" />
        )}
        <div ref={outputEndRef} />
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-t border-[var(--zai-border)]">
        <span className="text-[12px] text-[#00d4ff] shrink-0">$</span>
        <input
          ref={inputRef}
          value={cmdInput}
          onChange={(e) => setCmdInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter command..."
          aria-label="Terminal command input"
          disabled={loading}
          className="flex-1 bg-transparent text-[12px] text-[#e0e0e0] placeholder-[#3a3a3a] outline-none font-mono disabled:opacity-30"
          style={{ fontFamily: "inherit" }}
        />
        <button
          onClick={executeCommand}
          disabled={!cmdInput.trim() || loading}
          className="p-1 text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] disabled:opacity-10 transition-colors"
          aria-label="Run command"
        >
          <Play size={12} />
        </button>
      </div>
    </div>
  );
}

// ─── Task Planner Panel ──────────────────────────────────────────────────────

function TaskPlannerPanel({ onExecuteTool }: { onExecuteTool: (toolName: string, args: Record<string, unknown>, skipConfirm?: boolean) => Promise<string> }) {
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskStatus, setNewTaskStatus] = useState("pending");
  const [activePlanId, setActivePlanId] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      // Try bridge first
      const result = await onExecuteTool("listar_tareas", {}, true);
      const parsed = JSON.parse(result);
      if (Array.isArray(parsed)) {
        setTasks(parsed.map((t: any) => ({
          id: t.id || generateId(),
          title: t.title || t.titulo || t.name || "Untitled",
          status: t.status || t.estado || "pending",
          description: t.description || t.descripcion,
          planId: t.planId || t.plan_id || "",
        })));
      } else if (parsed.tareas || parsed.tasks) {
        const taskList = parsed.tareas || parsed.tasks;
        setTasks(taskList.map((t: any) => ({
          id: t.id || generateId(),
          title: t.title || t.titulo || t.name || "Untitled",
          status: t.status || t.estado || "pending",
          description: t.description || t.descripcion,
          planId: t.planId || t.plan_id || "",
        })));
      }
    } catch {
      // Fallback: try local DB via /api/plans
      try {
        const res = await fetch("/api/plans?limit=1");
        if (res.ok) {
          const data = await res.json();
          if (data.plans && data.plans.length > 0) {
            const plan = data.plans[0];
            setActivePlanId(plan.id);
            const tasksRes = await fetch(`/api/plans/${plan.id}/tasks`);
            if (tasksRes.ok) {
              const tasksData = await tasksRes.json();
              setTasks((tasksData.tasks || []).map((t: any) => ({
                id: t.id,
                title: t.title,
                status: t.status,
                description: t.description,
                planId: t.planId,
              })));
            }
          }
        }
      } catch {
        // No tasks available
      }
    }
    setLoading(false);
  }, [onExecuteTool]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchTasks();
  }, [fetchTasks]);

  const createTask = async () => {
    if (!newTaskTitle.trim()) return;
    setLoading(true);

    try {
      // Try bridge first
      await onExecuteTool("planificar_tarea", {
        titulo: newTaskTitle,
        estado: newTaskStatus,
      });
    } catch {
      // Fallback: use local DB
      try {
        let planId = activePlanId;
        if (!planId) {
          const res = await fetch("/api/plans", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ goal: "Task Board" }),
          });
          if (res.ok) {
            const plan = await res.json();
            planId = plan.id;
            setActivePlanId(planId);
          }
        }
        if (planId) {
          await fetch(`/api/plans/${planId}/tasks`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: newTaskTitle, status: newTaskStatus }),
          });
        }
      } catch {
        toast.error("Failed to create task");
      }
    }

    setNewTaskTitle("");
    await fetchTasks();
  };

  const moveTask = async (taskId: string, newStatus: string) => {
    // Optimistic update
    setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: newStatus } : t));

    // Try to persist
    try {
      const task = tasks.find((t) => t.id === taskId);
      if (task?.planId) {
        await fetch(`/api/plans/${task.planId}/tasks/${taskId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: newStatus }),
        });
      }
    } catch {
      // Silently fail - optimistic update already applied
    }
  };

  const deleteTask = async (taskId: string) => {
    // Optimistic update
    setTasks((prev) => prev.filter((t) => t.id !== taskId));

    // Try to persist
    try {
      const task = tasks.find((t) => t.id === taskId);
      if (task?.planId) {
        await fetch(`/api/plans/${task.planId}/tasks/${taskId}`, {
          method: "DELETE",
        });
      }
    } catch {
      toast.error("Failed to delete task");
    }
  };

  const columns = [
    { id: "pending", label: "PENDING", color: "border-[#888]" },
    { id: "in_progress", label: "IN PROGRESS", color: "border-[#00d4ff]" },
    { id: "completed", label: "COMPLETED", color: "border-[#00ff88]" },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--zai-border)]">
        <ListTodo size={13} className="text-[var(--zai-accent)]" />
        <span className="text-[11px] tracking-[0.15em] text-[var(--zai-text)] uppercase font-bold">TASKS</span>
        <span className="text-[9px] text-[var(--zai-text-dim)] ml-1">{tasks.length}</span>
        <div className="flex-1" />
        <button onClick={fetchTasks} className="p-1 text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] transition-colors" title="Refresh tasks" aria-label="Refresh tasks">
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Add task */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[rgba(255,255,255,0.04)]">
        <Input
          value={newTaskTitle}
          onChange={(e) => setNewTaskTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && createTask()}
          placeholder="New task..."
          aria-label="New task title"
          className="h-7 text-[11px] bg-[var(--zai-bg)] border-[var(--zai-border)] text-[var(--zai-text)] placeholder:text-[var(--zai-text-dim)]"
          style={{ fontFamily: "inherit" }}
        />
        <select
          value={newTaskStatus}
          onChange={(e) => setNewTaskStatus(e.target.value)}
          aria-label="Task status"
          className="bg-transparent text-[10px] text-[var(--zai-text-dim)] outline-none cursor-pointer border border-[var(--zai-border)] px-2 py-1"
          style={{ fontFamily: "inherit" }}
        >
          <option value="pending" className="bg-[var(--zai-bg-subtle)] text-[var(--zai-text)]">Pending</option>
          <option value="in_progress" className="bg-[var(--zai-bg-subtle)] text-[var(--zai-text)]">In Progress</option>
          <option value="completed" className="bg-[var(--zai-bg-subtle)] text-[var(--zai-text)]">Completed</option>
        </select>
        <button
          onClick={createTask}
          disabled={!newTaskTitle.trim() || loading}
          className="flex items-center gap-1 px-2.5 py-1 border border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[9px] text-[var(--zai-accent)] tracking-wider hover:bg-[rgba(0,212,255,0.1)] disabled:opacity-30 transition-colors"
        >
          <Plus size={10} />
          ADD
        </button>
      </div>

      {/* Kanban Board */}
      <div className="flex-1 overflow-x-auto p-4">
        {loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-[11px] text-[var(--zai-text-dim)] animate-pulse">Loading tasks...</span>
          </div>
        ) : (
          <div className="flex gap-4 h-full min-w-max">
            {columns.map((col) => {
              const colTasks = tasks.filter((t) => t.status === col.id);
              return (
                <div key={col.id} className="w-64 flex flex-col min-h-0">
                  <div className={`flex items-center gap-2 px-2 py-1.5 border-b-2 ${col.color} mb-2`}>
                    <span className="text-[10px] tracking-[0.15em] text-[var(--zai-text-dim)] uppercase">{col.label}</span>
                    <span className="text-[9px] text-[var(--zai-text-dim)] ml-auto">{colTasks.length}</span>
                  </div>
                  <div className="flex-1 overflow-y-auto space-y-2 max-h-full">
                    {colTasks.map((task) => (
                      <div
                        key={task.id}
                        className="px-3 py-2 border border-[var(--zai-border)] bg-[rgba(255,255,255,0.02)] hover:bg-[rgba(255,255,255,0.04)] transition-colors group"
                      >
                        <div className="text-[11px] text-[var(--zai-text)] leading-[1.5]">{task.title}</div>
                        {task.description && (
                          <div className="text-[9px] text-[var(--zai-text-dim)] mt-1 line-clamp-2">{task.description}</div>
                        )}
                        <div className="flex items-center gap-1 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          {col.id !== "pending" && (
                            <button
                              onClick={() => moveTask(task.id, col.id === "in_progress" ? "pending" : "in_progress")}
                              className="text-[8px] text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] px-1 border border-[var(--zai-border)] transition-colors"
                            >
                              ← BACK
                            </button>
                          )}
                          {col.id !== "completed" && (
                            <button
                              onClick={() => moveTask(task.id, col.id === "pending" ? "in_progress" : "completed")}
                              className="text-[8px] text-[var(--zai-text-dim)] hover:text-[#00ff88] px-1 border border-[var(--zai-border)] transition-colors"
                            >
                              {col.id === "pending" ? "START →" : "DONE →"}
                            </button>
                          )}
                          <button
                            onClick={() => deleteTask(task.id)}
                            className="text-[8px] text-[var(--zai-text-dim)] hover:text-[var(--zai-red)] px-1 border border-[var(--zai-border)] transition-colors ml-auto"
                            aria-label="Delete task"
                          >
                            <Trash2 size={8} />
                          </button>
                        </div>
                      </div>
                    ))}
                    {colTasks.length === 0 && (
                      <div className="text-[9px] text-[var(--zai-text-dim)] text-center py-4 opacity-30">No tasks</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Confirmation Dialog ─────────────────────────────────────────────────────

function ConfirmationDialog({
  pending,
  onResolve,
  sessionRemembered,
}: {
  pending: PendingConfirmation | null;
  onResolve: (allowed: boolean, remember: boolean) => void;
  sessionRemembered: Set<string>;
}) {
  const [remember, setRemember] = useState(false);

  if (!pending) return null;

  // Auto-allow if already remembered for this session
  if (sessionRemembered.has(pending.toolName)) {
    onResolve(true, false);
    return null;
  }

  return (
    <Dialog open={!!pending} onOpenChange={() => onResolve(false, false)}>
      <DialogContent className="sm:max-w-[440px] bg-[var(--zai-bg-subtle)] border-[var(--zai-border)] text-[var(--zai-text)]" style={{ fontFamily: "inherit" }}>
        <DialogHeader>
          <DialogTitle className="text-[13px] tracking-[0.15em] text-[var(--zai-red)] flex items-center gap-2">
            <AlertTriangle size={14} />
            CONFIRM ACTION
          </DialogTitle>
          <DialogDescription className="text-[11px] text-[var(--zai-text-dim)]">
            This action may modify your system. Please review before allowing.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div className="px-3 py-2 border border-[rgba(255,51,51,0.2)] bg-[rgba(255,51,51,0.03)]">
            <div className="flex items-center gap-2 mb-1.5">
              <Wrench size={10} className="text-[var(--zai-red)]" />
              <span className="text-[11px] text-[var(--zai-red)] font-bold">{pending.toolName}</span>
            </div>
            {pending.arguments && Object.keys(pending.arguments).length > 0 && (
              <pre className="text-[10px] text-[var(--zai-text-dim)] leading-[1.5] whitespace-pre-wrap max-h-32 overflow-y-auto">
                {JSON.stringify(pending.arguments, null, 2)}
              </pre>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="remember-check"
              checked={remember}
              onCheckedChange={(v) => setRemember(v === true)}
              className="border-[var(--zai-border)]"
            />
            <Label htmlFor="remember-check" className="text-[10px] text-[var(--zai-text-dim)] cursor-pointer">
              Remember for this session
            </Label>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button
            onClick={() => onResolve(false, false)}
            className="flex-1 px-3 py-2 border border-[var(--zai-border)] text-[10px] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] hover:bg-[var(--zai-bg-elevated)] transition-colors tracking-wider"
          >
            DENY
          </button>
          <button
            onClick={() => onResolve(true, remember)}
            className="flex-1 px-3 py-2 border border-[rgba(0,255,136,0.3)] bg-[rgba(0,255,136,0.05)] text-[10px] text-[#00ff88] hover:bg-[rgba(0,255,136,0.1)] transition-colors tracking-wider"
          >
            ALLOW
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Advanced Module Status Component ──────────────────────────────────────

function AdvancedModuleStatus({ name, endpoint }: { name: string; endpoint: string }) {
  const [status, setStatus] = useState<"loading" | "available" | "unavailable">("loading");
  const [details, setDetails] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const check = async () => {
      try {
        // Use Next.js API route proxy instead of calling bridge directly (B6 fix)
        const res = await fetch(endpoint, { signal: AbortSignal.timeout(5000) });
        if (res.ok) {
          const data = await res.json();
          setDetails(data);
          setStatus(data.available !== false ? "available" : "unavailable");
        } else {
          setStatus("unavailable");
        }
      } catch {
        setStatus("unavailable");
      }
    };
    check();
    const interval = setInterval(check, 30000); // Re-check every 30s
    return () => clearInterval(interval);
  }, [endpoint]);

  return (
    <div className="flex items-center justify-between">
      <span className="text-[9px] text-[var(--zai-text-dim)]">{name}</span>
      <div className="flex items-center gap-1">
        <Circle
          size={4}
          className={
            status === "available"
              ? "fill-[#00ff88] text-[#00ff88]"
              : status === "unavailable"
              ? "fill-[#ff3333] text-[#ff3333]"
              : "fill-[#ffd93d] text-[#ffd93d]"
          }
        />
        <span className="text-[9px] text-[var(--zai-text-dim)]">
          {status === "loading" ? "..." : status === "available" ? "OK" : "OFF"}
        </span>
      </div>
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

  // Panel mode state
  const [panelMode, setPanelMode] = useState<PanelMode>("chat");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [sessionRemembered, setSessionRemembered] = useState<Set<string>>(new Set());

  // Settings & Memory state
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [bridgeConfig, setBridgeConfig] = useState<BridgeConfig | null>(null);
  const [memoryExpanded, setMemoryExpanded] = useState(true);
  const [memoryStats, setMemoryStats] = useState<MemoryStats>({ total: 0, short_term: 0, medium_term: 0, long_term: 0 });
  const [memoryViewerOpen, setMemoryViewerOpen] = useState(false);
  const [clearMemoryAlertOpen, setClearMemoryAlertOpen] = useState(false);

  // Conversation state
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationsExpanded, setConversationsExpanded] = useState(true);
  const [loadingConversation, setLoadingConversation] = useState(false);

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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (isMobile) setSidebarOpen(false);
  }, [isMobile]);

  // ─── Fetch Conversations ────────────────────────────────────────────────

  const fetchConversations = useCallback(async () => {
    try {
      const res = await fetch("/api/conversations");
      if (res.ok) {
        const data = await res.json();
        setConversations(data.conversations || []);
      }
    } catch {
      // Conversations not available
    }
  }, []);

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
      toast.error("Failed to connect to agent");
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchTools();
    const interval = setInterval(fetchTools, 30000);
    return () => clearInterval(interval);
  }, [fetchTools]);

  // ─── Fetch Config ─────────────────────────────────────────────────────

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch("/api/config");
      if (res.ok) {
        const data = await res.json();
        if (data.bridgeConfig) {
          setBridgeConfig(data.bridgeConfig as BridgeConfig);
        }
      }
    } catch {
      // Config not available
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchConfig();
    const interval = setInterval(fetchConfig, 30000);
    return () => clearInterval(interval);
  }, [fetchConfig]);

  // ─── Fetch Memory Stats ────────────────────────────────────────────────

  const fetchMemoryStats = useCallback(async () => {
    try {
      const [allRes, shortRes, medRes, longRes] = await Promise.all([
        fetch("/api/memory?limit=1"),
        fetch("/api/memory?limit=1&type=short_term"),
        fetch("/api/memory?limit=1&type=working"),
        fetch("/api/memory?limit=1&type=long_term"),
      ]);
      const all = allRes.ok ? await allRes.json() : { total: 0 };
      const short = shortRes.ok ? await shortRes.json() : { total: 0 };
      const med = medRes.ok ? await medRes.json() : { total: 0 };
      const lng = longRes.ok ? await longRes.json() : { total: 0 };
      setMemoryStats({
        total: all.total || 0,
        short_term: short.total || 0,
        medium_term: med.total || 0,
        long_term: lng.total || 0,
      });
    } catch {
      // Memory stats not available
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchMemoryStats();
    const interval = setInterval(fetchMemoryStats, 15000);
    return () => clearInterval(interval);
  }, [fetchMemoryStats]);

  // Initial load of conversations
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchConversations().catch(() => {});
  }, [fetchConversations]);

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

  // ─── Context Usage ──────────────────────────────────────────────────────

  const contextUsage = useMemo(() => {
    const msgCount = messages.length;
    const pct = Math.min(100, Math.round((msgCount / MAX_CONVERSATION_MEMORY) * 100));
    return { msgCount, pct, max: MAX_CONVERSATION_MEMORY };
  }, [messages]);

  // ─── Create New Conversation ─────────────────────────────────────────────

  const createNewConversation = useCallback(async (title?: string): Promise<string | null> => {
    try {
      const res = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title || "New Conversation",
          model: selectedModel,
          mode: useAgent ? "agent" : "chat",
        }),
      });
      if (res.ok) {
        const conv = await res.json();
        await fetchConversations();
        return conv.id;
      }
    } catch {
      // Failed to create conversation
    }
    return null;
  }, [selectedModel, useAgent, fetchConversations]);

  // ─── Save Message to Conversation ────────────────────────────────────────

  const saveMessageToConversation = useCallback(async (
    conversationId: string,
    role: string,
    content: string,
    opts?: { thinking?: string; toolCalls?: ToolCall[]; tokenCount?: number; responseTime?: number }
  ) => {
    try {
      await fetch(`/api/conversations/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role,
          content,
          thinking: opts?.thinking || null,
          toolCalls: opts?.toolCalls || null,
          tokenCount: opts?.tokenCount || 0,
          responseTime: opts?.responseTime || null,
        }),
      });
    } catch {
      // Failed to save message
    }
  }, []);

  // ─── Delete Conversation ─────────────────────────────────────────────────

  const deleteConversation = useCallback(async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(`/api/conversations/${convId}`, { method: "DELETE" });
      if (res.ok) {
        if (activeConversationId === convId) {
          setActiveConversationId(null);
          setMessages([]);
          setSessionStats({ messageCount: 0, toolsUsed: 0, avgResponseTime: 0, totalTokens: 0 });
          responseTimesRef.current = [];
        }
        await fetchConversations();
        toast.success("Conversation deleted");
      }
    } catch {
      toast.error("Failed to delete conversation");
    }
  }, [activeConversationId, fetchConversations]);

  // ─── Load Conversation ───────────────────────────────────────────────────

  const loadConversation = useCallback(async (convId: string) => {
    setLoadingConversation(true);
    try {
      const res = await fetch(`/api/conversations/${convId}`);
      if (res.ok) {
        const data = await res.json();
        const loadedMessages: Message[] = (data.messages || []).map((m: any) => ({
          id: m.id || generateId(),
          role: m.role as "user" | "assistant",
          content: m.content,
          thinking: m.thinking || undefined,
          toolCalls: m.toolCalls ? (() => {
            try {
              return typeof m.toolCalls === "string" ? JSON.parse(m.toolCalls) : m.toolCalls;
            } catch { return undefined; }
          })() : undefined,
          timestamp: new Date(m.createdAt).getTime(),
          responseTime: m.responseTime || undefined,
          tokenCount: m.tokenCount || undefined,
        }));
        setMessages(loadedMessages);
        setActiveConversationId(convId);
        setSessionStats({
          messageCount: loadedMessages.filter((m: Message) => m.role === "assistant").length,
          toolsUsed: loadedMessages.reduce((acc: number, m: Message) => acc + (m.toolCalls?.length || 0), 0),
          avgResponseTime: loadedMessages.filter((m: Message) => m.responseTime).length > 0
            ? Math.round(loadedMessages.filter((m: Message) => m.responseTime).reduce((acc: number, m: Message) => acc + (m.responseTime || 0), 0) / loadedMessages.filter((m: Message) => m.responseTime).length)
            : 0,
          totalTokens: loadedMessages.reduce((acc: number, m: Message) => acc + (m.tokenCount || 0), 0),
        });
        responseTimesRef.current = loadedMessages
          .filter((m: Message) => m.responseTime)
          .map((m: Message) => m.responseTime!);
      }
    } catch {
      toast.error("Failed to load conversation");
    } finally {
      setLoadingConversation(false);
    }
  }, []);

  // ─── Start New Chat ─────────────────────────────────────────────────────

  const startNewChat = useCallback(() => {
    setActiveConversationId(null);
    setMessages([]);
    setSessionStats({ messageCount: 0, toolsUsed: 0, avgResponseTime: 0, totalTokens: 0 });
    responseTimesRef.current = [];
    inputRef.current?.focus();
  }, []);

  // ─── Handle Starter Click ────────────────────────────────────────────────

  const handleStarterClick = useCallback((prompt: string) => {
    setInput(prompt);
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  // ─── File Upload ────────────────────────────────────────────────────────

  const fileObjectsRef = useRef<File[]>([]);

  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB per file
  const MAX_TOTAL_SIZE = 100 * 1024 * 1024; // 100 MB total
  const DANGEROUS_EXTENSIONS = [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".scr", ".com", ".wsf"];

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    const newFiles: UploadedFile[] = [];
    const newFileObjects: File[] = [];
    let totalSize = uploadedFiles.reduce((sum, f) => sum + f.size, 0);
    let rejected = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const ext = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
      // Reject dangerous extensions
      if (DANGEROUS_EXTENSIONS.includes(ext)) {
        rejected++;
        continue;
      }
      // Reject oversized files
      if (file.size > MAX_FILE_SIZE) {
        toast.error(`${file.name} exceeds 50 MB limit`);
        rejected++;
        continue;
      }
      // Reject if total would exceed limit
      if (totalSize + file.size > MAX_TOTAL_SIZE) {
        toast.error("Total upload size exceeds 100 MB limit");
        break;
      }
      totalSize += file.size;
      newFiles.push({
        name: file.name,
        size: file.size,
        type: file.type,
      });
      newFileObjects.push(file);
    }
    if (rejected > 0) {
      toast.warning(`${rejected} file(s) rejected (unsafe type or too large)`);
    }
    if (newFiles.length > 0) {
      setUploadedFiles((prev) => [...prev, ...newFiles]);
      fileObjectsRef.current = [...fileObjectsRef.current, ...newFileObjects];
    }

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
    if (fileObjectsRef.current.length === 0) return uploadedFiles.map((f: any) => f.name);

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
        return names.length > 0 ? names : uploadedFiles.map((f: any) => f.name);
      }
    } catch {
      // Upload failed, still include file names in the message
    }

    return uploadedFiles.map((f: any) => f.name);
  };

  // ─── Voice Input ────────────────────────────────────────────────────────

  // D5 fix: Persist language preference for voice input and i18n
  const [userLanguage, setUserLanguage] = useState("es");

  // Load saved language on mount
  useEffect(() => {
    const saved = localStorage.getItem("agentlocal-language");
    if (saved) setUserLanguage(saved);
  }, []);

  const toggleVoiceInput = useCallback(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.error("Voice input is not supported in this browser. Try Chrome or Edge.");
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
    // D5 fix: Use persisted language preference instead of guessing from model name
    recognition.lang = userLanguage === "es" ? "es-ES" : "en-US";

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => (prev ? prev + " " + transcript : transcript));
      setIsRecording(false);
      toast.success("Voice input captured");
    };

    recognition.onerror = (event: any) => {
      setIsRecording(false);
      if (event.error === "not-allowed") {
        toast.error("Microphone access denied. Check browser permissions.");
      } else {
        toast.error(`Voice error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
    toast.info("Listening...");
  }, [isRecording, selectedModel]);

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

    // Ensure we have an active conversation
    let convId = activeConversationId;
    if (!convId) {
      // Auto-create a new conversation with first words of user message as title
      const title = userContent.slice(0, 50).replace(/\n/g, " ").trim();
      convId = await createNewConversation(title || "New Conversation");
      if (convId) {
        setActiveConversationId(convId);
      } else {
        // D7 fix: Warn if conversation creation failed - message won't be persisted
        toast.warning("Could not save conversation — message sent but not stored");
      }
    }

    // Save user message to conversation
    if (convId) {
      saveMessageToConversation(convId, "user", userContent);
    }

    const startTime = Date.now();

    // D12 fix: Truncate conversation history to respect MAX_CONVERSATION_MEMORY
    const maxMemory = bridgeConfig?.max_conversation_memory
      ? Number(bridgeConfig.max_conversation_memory)
      : MAX_CONVERSATION_MEMORY;
    const allMessages = [...messages, userMessage];
    const truncatedMessages = allMessages.length > maxMemory
      ? allMessages.slice(-maxMemory)
      : allMessages;
    const ollamaMessages = truncatedMessages.map((m) => ({
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
              // D2: Error filtering now done server-side
              let errVal = String(parsed.error);
              fullContent += `\nError: ${errVal}`;
              break;
            }

            // Bridge agent events (type field present)
            if (parsed.type) {
              if (parsed.type === "text") {
                // D2: Internal JSON filtering now done server-side.
                // Client receives pre-filtered text from backend.
                let content = parsed.data || "";
                if (!content.trim()) continue;
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
                  toolCalls.push({
                    name: toolName,
                    result: typeof toolResult === "string" ? toolResult : JSON.stringify(toolResult),
                    status: "success",
                  });
                }
              } else if (parsed.type === "meta") {
                const metaData = parsed.data;
                if (metaData) {
                  thinkingContent += (thinkingContent ? "\n" : "") + `[Meta] ${JSON.stringify(metaData)}`;
                }
              } else if (parsed.type === "done") {
                // Agent finished
              } else if (parsed.type === "error") {
                // D2+D10: Error filtering now done server-side
                let errMsg = String(parsed.data || '');
                fullContent += `\nError: ${errMsg}`;
              } else if (parsed.type === "warning") {
                // D1: Handle warning events (e.g., bridge fallback notification)
                const warningMsg = String(parsed.data || '');
                fullContent += `⚠ ${warningMsg}`;
              }
            } else {
              // Direct Ollama format (no type field)
              // D2: Internal JSON filtering now happens server-side,
              // but keep minimal client-side fallback for edge cases
              let content = parsed.message?.content || "";
              tokenCount++;

              if (!content.trim()) continue;

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

              // D4 fix: REMOVED fragile regex tool detection from plain text.
              // Tool calls are now only tracked via structured events (tool_start/tool_result)
              // from the bridge, not from bracket patterns like [example].
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

      // Auto-save assistant message to conversation
      if (convId && fullContent) {
        saveMessageToConversation(convId, "assistant", fullContent, {
          thinking: thinkingContent || undefined,
          toolCalls: finalToolCalls.length > 0 ? finalToolCalls : undefined,
          tokenCount,
          responseTime,
        });
        // Refresh conversation list to update title/date
        fetchConversations();
      }
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
    setActiveConversationId(null);
    setSessionStats({
      messageCount: 0,
      toolsUsed: 0,
      avgResponseTime: 0,
      totalTokens: 0,
    });
    responseTimesRef.current = [];
    setExpandedThinking({});
    // D6 fix: Consistent clear - always try both memory clear and reset
    let clearSuccess = true;
    try {
      const [memRes, resetRes] = await Promise.allSettled([
        fetch("/api/memory/clear", { method: "POST" }),
        fetch("/api/reset", { method: "POST" }),
      ]);
      if (memRes.status === "rejected" && resetRes.status === "rejected") {
        clearSuccess = false;
      }
    } catch {
      clearSuccess = false;
    }
    if (clearSuccess) {
      toast.success("Chat cleared");
    } else {
      toast.warning("Chat cleared locally — could not reach bridge");
    }
  };

  // ─── Save Config ─────────────────────────────────────────────────────

  const saveConfig = useCallback(async (key: string, value: string, category?: string) => {
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value, category: category || "general" }),
      });
      if (res.ok) {
        toast.success(`Config saved: ${key}`);
        fetchConfig(); // Refresh bridge config
      }
    } catch {
      toast.error(`Failed to save config: ${key}`);
    }
  }, [fetchConfig]);

  // ─── Switch Model ────────────────────────────────────────────────────

  const switchModel = useCallback(async (modelName: string) => {
    setSelectedModel(modelName);
    try {
      await fetch("/api/models/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelName }),
      });
      toast.success(`Switched to ${modelName}`);
    } catch {
      // Model switch on bridge failed - local switch is sufficient
    }
  }, []);

  // ─── Clear Memory ────────────────────────────────────────────────────

  const clearAllMemory = useCallback(async () => {
    try {
      const res = await fetch("/api/memory/clear", { method: "POST" });
      if (res.ok) {
        toast.success("Memory cleared");
        fetchMemoryStats();
      } else {
        // If bridge clear fails, try local DB clear
        try {
          await fetch("/api/memory?expiredOnly=true", { method: "DELETE" });
          toast.success("Local memory cleared");
          fetchMemoryStats();
        } catch {
          toast.error("Failed to clear memory");
        }
      }
    } catch {
      toast.error("Failed to clear memory");
    }
    setClearMemoryAlertOpen(false);
  }, [fetchMemoryStats]);

  // ─── Execute Tool with Confirmation ──────────────────────────────────

  // D3 fix: Comprehensive dangerous tool detection (EN + ES)
  const DANGEROUS_TOOL_PATTERNS = [
    // Spanish tool prefixes (from Python agent)
    { prefix: "ejecutar_", label: "Execute command" },
    { prefix: "matar_", label: "Kill process" },
    // Spanish tool exact names
    { exact: "escribir_archivo", label: "Write file" },
    { exact: "buscar_reemplazar", label: "Search & replace" },
    { exact: "eliminar_archivo", label: "Delete file" },
    { exact: "mover_archivo", label: "Move file" },
    // English equivalents
    { exact: "execute_command", label: "Execute command" },
    { exact: "run_command", label: "Run command" },
    { exact: "write_file", label: "Write file" },
    { exact: "delete_file", label: "Delete file" },
    { exact: "shell_exec", label: "Shell execute" },
    { exact: "bash_exec", label: "Bash execute" },
  ];

  const DANGEROUS_GIT_OPS = ["push", "reset", "checkout", "clean", "rebase", "cherry-pick", "stash drop", "branch -D"];

  const executeTool = useCallback(async (
    toolName: string,
    args: Record<string, unknown>,
    skipConfirm?: boolean
  ): Promise<string> => {
    // D3 fix: Check both ES and EN dangerous patterns
    const isDangerous = !skipConfirm && (
      DANGEROUS_TOOL_PATTERNS.some(p =>
        p.prefix ? toolName.startsWith(p.prefix) : toolName === p.exact
      ) ||
      (toolName === "git_operacion" && DANGEROUS_GIT_OPS.some(op =>
        String(args.operacion || "").includes(op)
      )) ||
      (toolName === "git_operation" && DANGEROUS_GIT_OPS.some(op =>
        String(args.operation || args.operacion || "").includes(op)
      ))
    );

    // D9 fix: Add timeout to confirmation promise (5 min auto-deny)
    if (isDangerous && !sessionRemembered.has(toolName)) {
      return new Promise<string>((resolve) => {
        const CONFIRMATION_TIMEOUT = 5 * 60 * 1000; // 5 minutes
        let resolved = false;

        const timeoutId = setTimeout(() => {
          if (!resolved) {
            resolved = true;
            setPendingConfirmation(null);
            resolve(JSON.stringify({ error: "Action timed out — confirmation dismissed" }));
            toast.warning(`Tool "${toolName}" timed out waiting for confirmation`);
          }
        }, CONFIRMATION_TIMEOUT);

        setPendingConfirmation({
          toolName,
          arguments: args,
          resolve: (allowed: boolean) => {
            if (resolved) return; // Already timed out
            resolved = true;
            clearTimeout(timeoutId);
            if (!allowed) {
              resolve(JSON.stringify({ error: "Action denied by user" }));
            } else {
              // Execute the tool
              fetch("/api/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tool_name: toolName, arguments: args }),
              })
                .then((res) => res.json())
                .then((data) => resolve(JSON.stringify(data)))
                .catch((err) => resolve(JSON.stringify({ error: String(err) })));
            }
          },
        });
      });
    }

    try {
      const res = await fetch("/api/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_name: toolName, arguments: args }),
      });
      const data = await res.json();
      return JSON.stringify(data);
    } catch (err) {
      return JSON.stringify({ error: String(err) });
    }
  }, [sessionRemembered]);

  const resolveConfirmation = useCallback((allowed: boolean, remember: boolean) => {
    if (pendingConfirmation) {
      if (remember && allowed) {
        setSessionRemembered((prev) => new Set(prev).add(pendingConfirmation.toolName));
      }
      pendingConfirmation.resolve(allowed);
      setPendingConfirmation(null);
    }
  }, [pendingConfirmation]);

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div
      className="h-screen flex flex-col bg-[var(--zai-bg)] text-[var(--zai-text)] overflow-hidden"
      style={{
        fontFamily:
          "var(--font-geist-mono), 'JetBrains Mono', 'Fira Code', ui-monospace, monospace",
      }}
    >
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "var(--zai-bg-elevated)",
            color: "var(--zai-text)",
            border: "1px solid var(--zai-border)",
            fontFamily: "inherit",
            fontSize: "12px",
          },
        }}
      />
      {/* ─── Top Bar ─────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between h-9 px-4 border-b border-[var(--zai-border)] shrink-0 select-none">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 bg-[var(--zai-accent-dim)]" />
            <span className="text-[11px] tracking-[0.3em] text-[var(--zai-text)] font-bold">
              AGENTLOCAL
            </span>
          </div>
          <span className="text-[10px] text-[var(--zai-text-dim)]">│</span>
          <span className="text-[11px] text-[var(--zai-text-dim)]">{selectedModel}</span>
          <div className="flex items-center gap-1.5 ml-1">
            <Circle
              size={5}
              className={
                status.connected
                  ? "fill-[#00ff88] text-[#00ff88]"
                  : "fill-[#ff3333] text-[#ff3333]"
              }
            />
            <span className="text-[10px] text-[var(--zai-text-dim)] tracking-wider">
              {status.connected ? "CONNECTED" : "OFFLINE"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Theme Toggle */}
          <ThemeToggleButton />
          {/* Settings button */}
          <button
            onClick={() => setSettingsOpen(true)}
            className="p-1.5 text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] transition-colors duration-150"
            aria-label="Open settings"
            title="Settings"
          >
            <Settings size={14} />
          </button>
          {/* Agent mode toggle */}
          <button
            onClick={() => setUseAgent(!useAgent)}
            className={`text-[10px] tracking-wider px-2.5 py-0.5 border transition-colors duration-150 ${
              useAgent
                ? "text-[var(--zai-accent)] border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)]"
                : "text-[var(--zai-text-dim)] border-[var(--zai-border)] hover:text-[var(--zai-text)] hover:border-[var(--zai-border)]"
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
              className="text-[10px] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] transition-colors px-2 py-0.5 border border-[var(--zai-border)] hover:border-[var(--zai-border)]"
              aria-label="Clear chat and memory"
              title={useAgent ? "Clear chat view and agent memory" : "Clear chat view"}
            >
              CLEAR
            </button>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] transition-colors duration-150"
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

      {/* ─── Settings Dialog ────────────────────────────────────────────── */}
      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        selectedModel={selectedModel}
        bridgeConfig={bridgeConfig}
        onSaveConfig={saveConfig}
        userLanguage={userLanguage}
        setUserLanguage={setUserLanguage}
      />

      {/* ─── Memory Viewer Dialog ───────────────────────────────────────── */}
      <MemoryViewerDialog
        open={memoryViewerOpen}
        onOpenChange={setMemoryViewerOpen}
      />

      {/* ─── Clear Memory Alert ─────────────────────────────────────────── */}
      <AlertDialog open={clearMemoryAlertOpen} onOpenChange={setClearMemoryAlertOpen}>
        <AlertDialogContent className="bg-[var(--zai-bg-subtle)] border-[var(--zai-border)] text-[var(--zai-text)]" style={{ fontFamily: "inherit" }}>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-[13px] tracking-[0.15em]">CLEAR ALL MEMORY?</AlertDialogTitle>
            <AlertDialogDescription className="text-[11px] text-[var(--zai-text-dim)]">
              This will permanently delete all agent memory entries. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="text-[10px] border-[var(--zai-border)] bg-[var(--zai-bg)] hover:bg-[var(--zai-bg-elevated)] text-[var(--zai-text)]">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={clearAllMemory} className="text-[10px] bg-[var(--zai-red)] hover:bg-[var(--zai-red)]/80 text-white">Clear Memory</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ─── Confirmation Dialog ─────────────────────────────────────────── */}
      <ConfirmationDialog
        pending={pendingConfirmation}
        onResolve={resolveConfirmation}
        sessionRemembered={sessionRemembered}
      />

      {/* ─── Main Content ────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* ─── Main Area (Chat or Panel) ──────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0">
          {panelMode === "chat" ? (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
                {messages.length === 0 && (
                  <WelcomeScreen
                    status={status}
                    selectedModel={selectedModel}
                    useAgent={useAgent}
                    onStarterClick={handleStarterClick}
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
                  {uploadedFiles.map((file: any, i: number) => (
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
                    accept=".txt,.md,.py,.js,.ts,.tsx,.jsx,.json,.csv,.xml,.yaml,.yml,.html,.css,.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.svg,.webp,.zip,.tar,.gz,.c,.cpp,.h,.hpp,.java,.rb,.go,.rs,.sh,.bash,.sql,.r,.ipynb"
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
            </>
          ) : panelMode === "files" ? (
            <FileExplorerPanel onExecuteTool={executeTool} />
          ) : panelMode === "git" ? (
            <GitPanel onExecuteTool={executeTool} />
          ) : panelMode === "terminal" ? (
            <TerminalPanel onExecuteTool={executeTool} />
          ) : panelMode === "tasks" ? (
            <TaskPlannerPanel onExecuteTool={executeTool} />
          ) : null}
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
          } shrink-0 border-l border-[var(--zai-border)] bg-[var(--zai-sidebar)] overflow-hidden transition-all duration-200`}
        >
          <div className="w-64 h-full overflow-y-auto px-4 py-4 space-y-5">
            {/* PANELS NAV */}
            <section>
              <div className="flex items-center gap-1.5 mb-2.5">
                <Shield size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  Panels
                </h3>
              </div>
              <div className="grid grid-cols-5 gap-1">
                <button
                  onClick={() => setPanelMode("chat")}
                  className={`flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 border transition-colors ${
                    panelMode === "chat"
                      ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[var(--zai-accent)]"
                      : "border-[var(--zai-border)] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] hover:border-[var(--zai-border)]"
                  }`}
                  title="Chat"
                  aria-label="Switch to chat panel"
                >
                  <MessageSquare size={11} />
                  <span className="text-[7px] tracking-wider">CHAT</span>
                </button>
                <button
                  onClick={() => setPanelMode("files")}
                  className={`flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 border transition-colors ${
                    panelMode === "files"
                      ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[var(--zai-accent)]"
                      : "border-[var(--zai-border)] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] hover:border-[var(--zai-border)]"
                  }`}
                  title="Files"
                  aria-label="Switch to file explorer panel"
                >
                  <Folder size={11} />
                  <span className="text-[7px] tracking-wider">FILES</span>
                </button>
                <button
                  onClick={() => setPanelMode("git")}
                  className={`flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 border transition-colors ${
                    panelMode === "git"
                      ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[var(--zai-accent)]"
                      : "border-[var(--zai-border)] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] hover:border-[var(--zai-border)]"
                  }`}
                  title="Git"
                  aria-label="Switch to git panel"
                >
                  <GitBranch size={11} />
                  <span className="text-[7px] tracking-wider">GIT</span>
                </button>
                <button
                  onClick={() => setPanelMode("terminal")}
                  className={`flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 border transition-colors ${
                    panelMode === "terminal"
                      ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[var(--zai-accent)]"
                      : "border-[var(--zai-border)] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] hover:border-[var(--zai-border)]"
                  }`}
                  title="Terminal"
                  aria-label="Switch to terminal panel"
                >
                  <Terminal size={11} />
                  <span className="text-[7px] tracking-wider">TERM</span>
                </button>
                <button
                  onClick={() => setPanelMode("tasks")}
                  className={`flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 border transition-colors ${
                    panelMode === "tasks"
                      ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)] text-[var(--zai-accent)]"
                      : "border-[var(--zai-border)] text-[var(--zai-text-dim)] hover:text-[var(--zai-text)] hover:border-[var(--zai-border)]"
                  }`}
                  title="Tasks"
                  aria-label="Switch to task planner panel"
                >
                  <ListTodo size={11} />
                  <span className="text-[7px] tracking-wider">TASKS</span>
                </button>
              </div>
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* CONVERSATIONS */}
            <section>
              <button
                onClick={() => setConversationsExpanded(!conversationsExpanded)}
                className="flex items-center gap-1.5 mb-3 w-full"
              >
                <FolderOpen size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  Conversations
                </h3>
                <span className="text-[9px] text-[var(--zai-text-dim)] ml-auto">
                  {conversations.length}
                </span>
                {conversationsExpanded ? (
                  <ChevronDown size={9} className="text-[var(--zai-text-dim)]" />
                ) : (
                  <ChevronRight size={9} className="text-[var(--zai-text-dim)]" />
                )}
              </button>

              {conversationsExpanded && (
                <div className="space-y-1">
                  {/* New Chat button */}
                  <button
                    onClick={startNewChat}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 border transition-all duration-150 ${
                      !activeConversationId
                        ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)]"
                        : "border-[var(--zai-border)] hover:border-[var(--zai-border)] hover:bg-[var(--zai-bg-elevated)]"
                    }`}
                  >
                    <Plus size={10} className={!activeConversationId ? "text-[var(--zai-accent)]" : "text-[var(--zai-text-dim)]"} />
                    <span className={`text-[10px] ${!activeConversationId ? "text-[var(--zai-accent)]" : "text-[var(--zai-text-dim)]"}`}>
                      New Chat
                    </span>
                  </button>

                  {/* Conversation list */}
                  <div className="max-h-52 overflow-y-auto space-y-0.5">
                    {loadingConversation ? (
                      <div className="text-[9px] text-[var(--zai-text-dim)] px-2 py-1.5">
                        Loading...
                      </div>
                    ) : conversations.length === 0 ? (
                      <div className="text-[9px] text-[var(--zai-text-dim)] px-2 py-1.5">
                        No conversations yet
                      </div>
                    ) : (
                      conversations.map((conv) => (
                        <div
                          key={conv.id}
                          onClick={() => loadConversation(conv.id)}
                          className={`group flex items-center gap-1.5 px-2 py-1.5 border cursor-pointer transition-all duration-150 ${
                            conv.id === activeConversationId
                              ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)]"
                              : "border-transparent hover:border-[var(--zai-border)] hover:bg-[var(--zai-bg-elevated)]"
                          }`}
                        >
                          <MessageSquare
                            size={9}
                            className={`shrink-0 ${
                              conv.id === activeConversationId
                                ? "text-[var(--zai-accent)]"
                                : "text-[var(--zai-text-dim)]"
                            }`}
                          />
                          <div className="flex-1 min-w-0">
                            <div
                              className={`text-[10px] truncate ${
                                conv.id === activeConversationId
                                  ? "text-[var(--zai-text)]"
                                  : "text-[var(--zai-text-dim)]"
                              }`}
                            >
                              {truncateTitle(conv.title)}
                            </div>
                            <div className="text-[8px] text-[var(--zai-text-dim)]">
                              {formatDate(conv.updatedAt)}
                              {conv._count && conv._count.messages > 0 && (
                                <span> · {conv._count.messages} msg{conv._count.messages !== 1 ? "s" : ""}</span>
                              )}
                            </div>
                          </div>
                          <button
                            onClick={(e) => deleteConversation(conv.id, e)}
                            className="opacity-0 group-hover:opacity-100 text-[var(--zai-text-dim)] hover:text-[var(--zai-red)] transition-all duration-150 shrink-0"
                            aria-label="Delete conversation"
                            title="Delete conversation"
                          >
                            <X size={9} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* SYSTEM */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Server size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  System
                </h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[var(--zai-text-dim)]">MODEL</span>
                  <select
                    value={selectedModel}
                    onChange={(e) => switchModel(e.target.value)}
                    className="bg-transparent text-[10px] text-[var(--zai-text)] outline-none cursor-pointer text-right appearance-none"
                    style={{ fontFamily: "inherit" }}
                  >
                    {status.models.length > 0 ? (
                      status.models.map((m) => (
                        <option
                          key={m.name}
                          value={m.name}
                          className="bg-[var(--zai-bg-subtle)] text-[var(--zai-text)]"
                        >
                          {m.name}
                        </option>
                      ))
                    ) : (
                      <option
                        value={selectedModel}
                        className="bg-[var(--zai-bg-subtle)] text-[var(--zai-text)]"
                      >
                        {selectedModel}
                      </option>
                    )}
                  </select>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[var(--zai-text-dim)]">HOST</span>
                  <span className="text-[11px] text-[var(--zai-text-dim)]">
                    localhost:11434
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[var(--zai-text-dim)]">STATUS</span>
                  <div className="flex items-center gap-1.5">
                    <Circle
                      size={4}
                      className={
                        status.connected
                          ? "fill-[#00ff88] text-[#00ff88]"
                          : "fill-[#ff3333] text-[#ff3333]"
                      }
                    />
                    <span className="text-[10px] text-[var(--zai-text-dim)]">
                      {status.connected ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[var(--zai-text-dim)]">UPTIME</span>
                  <span className="text-[11px] text-[var(--zai-text-dim)] tabular-nums">
                    {formatUptime(uptime)}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[var(--zai-text-dim)]">MODE</span>
                  <span
                    className={`text-[11px] ${
                      useAgent ? "text-[var(--zai-accent)]" : "text-[var(--zai-text-dim)]"
                    }`}
                  >
                    {useAgent ? "AGENT" : "CHAT"}
                  </span>
                </div>
                {useAgent && status.agentAvailable !== undefined && (
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[var(--zai-text-dim)]">BRIDGE</span>
                    <div className="flex items-center gap-1.5">
                      <Circle
                        size={4}
                        className={
                          status.agentAvailable
                            ? "fill-[#00ff88] text-[#00ff88]"
                            : "fill-[#ff8800] text-[#ff8800]"
                        }
                      />
                      <span className="text-[11px] text-[var(--zai-text-dim)]">
                        {status.agentAvailable ? "Active" : "Inactive"}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* HARDWARE */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Cpu size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  Hardware
                </h3>
              </div>
              <HardwareStats />
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* MEMORY */}
            <section>
              <button
                onClick={() => setMemoryExpanded(!memoryExpanded)}
                className="flex items-center gap-1.5 mb-3 w-full"
              >
                <Brain size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  Memory
                </h3>
                <span className="text-[9px] text-[var(--zai-text-dim)] ml-auto">
                  {memoryStats.total}
                </span>
                {memoryExpanded ? (
                  <ChevronDown size={9} className="text-[var(--zai-text-dim)]" />
                ) : (
                  <ChevronRight size={9} className="text-[var(--zai-text-dim)]" />
                )}
              </button>

              {memoryExpanded && (
                <div className="space-y-2.5">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[var(--zai-text-dim)]">TOTAL</span>
                    <span className="text-[11px] text-[var(--zai-text)] tabular-nums">{memoryStats.total}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[var(--zai-text-dim)]">SHORT-TERM</span>
                    <span className="text-[11px] text-[var(--zai-accent)] tabular-nums">{memoryStats.short_term}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[var(--zai-text-dim)]">MEDIUM-TERM</span>
                    <span className="text-[11px] text-[var(--zai-green)] tabular-nums">{memoryStats.medium_term}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-[var(--zai-text-dim)]">LONG-TERM</span>
                    <span className="text-[11px] text-[#ffd93d] tabular-nums">{memoryStats.long_term}</span>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => setMemoryViewerOpen(true)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 border border-[var(--zai-border)] hover:border-[var(--zai-border-accent)] hover:bg-[var(--zai-accent-dim)] text-[9px] text-[var(--zai-text-dim)] hover:text-[var(--zai-accent)] transition-colors tracking-wider uppercase"
                    >
                      <Eye size={9} />
                      View All
                    </button>
                    <button
                      onClick={() => setClearMemoryAlertOpen(true)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 border border-[var(--zai-border)] hover:border-[var(--zai-red)] hover:bg-[rgba(255,51,51,0.05)] text-[9px] text-[var(--zai-text-dim)] hover:text-[var(--zai-red)] transition-colors tracking-wider uppercase"
                    >
                      <Trash2 size={9} />
                      Clear
                    </button>
                  </div>
                </div>
              )}
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* SESSION */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Zap size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  Session
                </h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <MessageSquare size={9} className="text-[var(--zai-text-dim)]" />
                    <span className="text-[10px] text-[var(--zai-text-dim)]">MESSAGES</span>
                  </div>
                  <span className="text-[11px] text-[var(--zai-text)] tabular-nums">
                    {sessionStats.messageCount}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Wrench size={9} className="text-[var(--zai-text-dim)]" />
                    <span className="text-[10px] text-[var(--zai-text-dim)]">TOOLS</span>
                  </div>
                  <span className="text-[11px] text-[var(--zai-text)] tabular-nums">
                    {sessionStats.toolsUsed}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Clock size={9} className="text-[var(--zai-text-dim)]" />
                    <span className="text-[10px] text-[var(--zai-text-dim)]">AVG RESP</span>
                  </div>
                  <span className="text-[10px] text-[var(--zai-text)] tabular-nums">
                    {sessionStats.avgResponseTime > 0
                      ? `${sessionStats.avgResponseTime}ms`
                      : "—"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Activity size={9} className="text-[var(--zai-text-dim)]" />
                    <span className="text-[10px] text-[var(--zai-text-dim)]">TOKENS</span>
                  </div>
                  <span className="text-[10px] text-[var(--zai-text)] tabular-nums">
                    {sessionStats.totalTokens > 0
                      ? `~${sessionStats.totalTokens}`
                      : "—"}
                  </span>
                </div>

                {/* Context Usage Indicator */}
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <div className="flex items-center gap-1">
                      <MemoryStick size={9} className="text-[var(--zai-text-dim)]" />
                      <span className="text-[10px] text-[var(--zai-text-dim)]">CONTEXT</span>
                    </div>
                    <span className={`text-[10px] tabular-nums ${
                      contextUsage.pct >= 90 ? "text-[var(--zai-red)]" :
                      contextUsage.pct >= 70 ? "text-[#ffd93d]" :
                      "text-[var(--zai-text-dim)]"
                    }`}>
                      {contextUsage.msgCount}/{contextUsage.max}
                    </span>
                  </div>
                  <div className="h-[3px] bg-[var(--zai-bg-elevated)] overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        contextUsage.pct >= 90
                          ? "bg-[var(--zai-red)]"
                          : contextUsage.pct >= 70
                          ? "bg-[rgba(255,217,61,0.4)]"
                          : "bg-[var(--zai-accent)]"
                      }`}
                      style={{ width: `${contextUsage.pct}%` }}
                    />
                  </div>
                </div>
              </div>
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* MODELS */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <HardDrive size={10} className="text-[var(--zai-text-dim)]" />
                <h3 className="text-[10px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                  Models
                </h3>
                {status.connected && (
                  <span className="text-[9px] text-[var(--zai-text-dim)] ml-auto">
                    {status.modelCount}
                  </span>
                )}
              </div>
              <div className="space-y-0.5 max-h-52 overflow-y-auto">
                {status.connected && status.models.length > 0 ? (
                  status.models.map((model) => {
                    const nameL = model.name.toLowerCase();
                    const supportsTools = nameL.includes("qwen") || nameL.includes("llama") || nameL.includes("mistral") || nameL.includes("command");
                    const sizeGB = (model.size / (1024 * 1024 * 1024)).toFixed(1);
                    return (
                      <button
                        key={model.name}
                        onClick={() => switchModel(model.name)}
                        className={`w-full text-left px-2 py-1.5 border transition-all duration-150 ${
                          model.name === selectedModel
                            ? "border-[var(--zai-border-accent)] bg-[var(--zai-accent-dim)]"
                            : "border-transparent hover:border-[var(--zai-border)] hover:bg-[var(--zai-bg-elevated)]"
                        }`}
                      >
                        <div className="flex justify-between items-center">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span
                              className={`text-[11px] truncate ${
                                model.name === selectedModel
                                  ? "text-[var(--zai-text)]"
                                  : "text-[var(--zai-text-dim)]"
                              }`}
                            >
                              {model.name}
                            </span>
                            {supportsTools && (
                              <Badge
                                variant="outline"
                                className="text-[7px] px-1 py-0 h-3.5 border-[var(--zai-border-accent)] text-[var(--zai-accent)] shrink-0"
                              >
                                TOOLS
                              </Badge>
                            )}
                          </div>
                          <span className="text-[9px] text-[var(--zai-text-dim)] shrink-0">
                            {sizeGB} GB
                          </span>
                        </div>
                        {model.parameter_size !== "unknown" && (
                          <div className="text-[9px] text-[var(--zai-text-dim)] mt-0.5">
                            {model.parameter_size} · {model.quantization_level}
                          </div>
                        )}
                      </button>
                    );
                  })
                ) : (
                  <div className="text-[10px] text-[var(--zai-text-dim)] px-2 py-1">
                    {status.connected
                      ? "No models found"
                      : "Cannot connect to Ollama"}
                  </div>
                )}
              </div>
            </section>

            <div className="h-px bg-[var(--zai-border)]" />

            {/* TOOLS */}
            {tools.length > 0 && (
              <section>
                <div className="flex items-center gap-1.5 mb-3">
                  <Wrench size={10} className="text-[var(--zai-text-dim)]" />
                  <h3 className="text-[10px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                    Tools
                  </h3>
                  <span className="text-[9px] text-[var(--zai-text-dim)] ml-auto">
                    {tools.length}
                  </span>
                </div>
                <div className="space-y-2 max-h-52 overflow-y-auto">
                  {Object.entries(toolsByCategory).map(
                    ([category, categoryTools]) => (
                      <div key={category}>
                        <div className="text-[9px] text-[var(--zai-text-dim)] tracking-[0.15em] uppercase mb-1">
                          {category}
                        </div>
                        <div className="space-y-0.5">
                          {categoryTools.map((tool) => (
                            <div
                              key={tool.name}
                              className="px-2 py-1 hover:bg-[var(--zai-bg-elevated)] transition-colors"
                            >
                              <div className="text-[10px] text-[var(--zai-text-dim)]">
                                {tool.name}
                              </div>
                              {tool.description && (
                                <div className="text-[9px] text-[var(--zai-text-dim)] truncate">
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
            <div className="pt-4">
              {/* ADVANCED MODULES STATUS */}
              <section>
                <div className="flex items-center gap-1.5 mb-2">
                  <Server size={9} className="text-[var(--zai-text-dim)]" />
                  <span className="text-[9px] tracking-[0.2em] text-[var(--zai-text-dim)] uppercase">
                    Advanced
                  </span>
                </div>
                <div className="space-y-1.5">
                  {[
                    { name: "Orchestrator", endpoint: "/api/orchestrator/status" },
                    { name: "Circuit Breaker", endpoint: "/api/circuit-breaker/status" },
                    { name: "Auto-Evolve", endpoint: "/api/auto-evolve" },
                    { name: "MCP Client", endpoint: "/api/mcp/status" },
                  ].map((mod) => (
                    <AdvancedModuleStatus key={mod.name} name={mod.name} endpoint={mod.endpoint} />
                  ))}
                </div>
              </section>
              <div className="mt-4 text-[8px] text-[var(--zai-text-dim)] text-center tracking-[0.4em] uppercase">
                AgentLocal v1.0
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
