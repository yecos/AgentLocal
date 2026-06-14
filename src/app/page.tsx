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
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedModel: string;
  bridgeConfig: BridgeConfig | null;
  onSaveConfig: (key: string, value: string | number | boolean, category?: string) => void;
}) {
  const { theme, setTheme } = useTheme();
  const [localConfig, setLocalConfig] = useState<BridgeConfig>({});
  const [language, setLanguage] = useState("ES");

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
                onValueChange={setLanguage}
              >
                <SelectTrigger className="h-7 text-[10px] w-24 bg-[var(--zai-bg)] border-[var(--zai-border)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--zai-bg-subtle)] border-[var(--zai-border)]">
                  <SelectItem value="ES" className="text-[10px]">Español</SelectItem>
                  <SelectItem value="EN" className="text-[10px]">English</SelectItem>
                </SelectContent>
              </Select>
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

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(true);
      fetch(`/api/memory?limit=100${searchQuery ? `&keyword=${encodeURIComponent(searchQuery)}` : ""}`)
        .then((res) => res.ok ? res.json() : { entries: [] })
        .then((data) => setEntries(data.entries || []))
        .catch(() => setEntries([]))
        .finally(() => setLoading(false));
    }
  }, [open, searchQuery]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px] bg-[var(--zai-bg-subtle)] border-[var(--zai-border)] text-[var(--zai-text)] max-h-[85vh] flex flex-col" style={{ fontFamily: "inherit" }}>
        <DialogHeader>
          <DialogTitle className="text-[13px] tracking-[0.15em] text-[var(--zai-text)]">
            MEMORY ENTRIES
          </DialogTitle>
          <DialogDescription className="text-[11px] text-[var(--zai-text-dim)]">
            {entries.length} entries stored in agent memory
          </DialogDescription>
        </DialogHeader>
        <div className="relative mt-2">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--zai-text-dim)]" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search memory..."
            className="pl-8 h-8 text-[11px] bg-[var(--zai-bg)] border-[var(--zai-border)] text-[var(--zai-text)] placeholder:text-[var(--zai-text-dim)]"
            style={{ fontFamily: "inherit" }}
          />
        </div>
        <div className="flex-1 overflow-y-auto mt-3 space-y-1.5 min-h-0 max-h-[50vh]">
          {loading ? (
            <div className="text-[10px] text-[var(--zai-text-dim)] text-center py-4">Loading...</div>
          ) : entries.length === 0 ? (
            <div className="text-[10px] text-[var(--zai-text-dim)] text-center py-4">No memory entries found</div>
          ) : (
            entries.map((entry) => (
              <div
                key={entry.id}
                className="px-3 py-2 border border-[var(--zai-border)] bg-[var(--zai-bg)]"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Badge
                    variant="outline"
                    className="text-[8px] px-1.5 py-0 h-4 border-[var(--zai-border-accent)] text-[var(--zai-accent)]"
                  >
                    {entry.type}
                  </Badge>
                  {entry.category && (
                    <span className="text-[8px] text-[var(--zai-text-dim)]">{entry.category}</span>
                  )}
                  <span className="text-[8px] text-[var(--zai-text-dim)] ml-auto">
                    {Math.round(entry.confidence * 100)}%
                  </span>
                </div>
                <div className="text-[10px] text-[var(--zai-text)] leading-[1.5] line-clamp-2">
                  {entry.content}
                </div>
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

    // Ensure we have an active conversation
    let convId = activeConversationId;
    if (!convId) {
      // Auto-create a new conversation with first words of user message as title
      const title = userContent.slice(0, 50).replace(/\n/g, " ").trim();
      convId = await createNewConversation(title || "New Conversation");
      if (convId) {
        setActiveConversationId(convId);
      }
    }

    // Save user message to conversation
    if (convId) {
      saveMessageToConversation(convId, "user", userContent);
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
                const trimmed = content.trim();
                if (trimmed.startsWith('{')) {
                  try {
                    const jsonObj = JSON.parse(trimmed);
                    content = jsonObj.respuesta_final || jsonObj.pensamiento || '';
                    if (!content) continue;
                  } catch {
                    if (trimmed.includes('"pensamiento"') || trimmed.includes('"accion"') || trimmed.includes('"respuesta_final"')) {
                      continue;
                    }
                  }
                }
                content = content.replace(/"?pensamiento"?\s*:\s*"?[^",}]*"?\s*,?\s*/g, '');
                content = content.replace(/"?accion"?\s*:\s*"?[^",}]*"?\s*,?\s*/g, '');
                content = content.replace(/"?respuesta_final"?\s*:\s*"?[^",}]*"?\s*,?\s*/g, '');
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

              const directTrimmed = content.trim();
              if (directTrimmed.startsWith('{')) {
                try {
                  const jsonObj = JSON.parse(directTrimmed);
                  content = jsonObj.respuesta_final || jsonObj.pensamiento || '';
                  if (!content) continue;
                } catch {
                  if (directTrimmed.includes('"pensamiento"') || directTrimmed.includes('"accion"') || directTrimmed.includes('"respuesta_final"')) {
                    continue;
                  }
                }
              }
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
    // Also clear agent memory via bridge (B2 fix)
    if (useAgent) {
      try {
        await fetch("/api/memory/clear", { method: "POST" });
      } catch {
        // Bridge not available - local clear is sufficient
      }
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
          } shrink-0 border-l border-[var(--zai-border)] bg-[var(--zai-sidebar)] overflow-hidden transition-all duration-200`}
        >
          <div className="w-64 h-full overflow-y-auto px-4 py-4 space-y-5">
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
            <div className="pt-6">
              <div className="text-[8px] text-[var(--zai-text-dim)] text-center tracking-[0.4em] uppercase">
                AgentLocal v1.0
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
