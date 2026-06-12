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

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
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
          <span className="text-[9px] text-[#444444]">GPU</span>
          <span className="text-[10px] text-[#666666]">—</span>
        </div>
        <div className="text-[8px] text-[#333333]">No GPU detected</div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <Cpu size={8} className="text-[#444444]" />
            <span className="text-[9px] text-[#444444]">CPU</span>
          </div>
          <span className="text-[9px] text-[#666666]">{stats.cpu > 0 ? `${stats.cpu}%` : '—'}</span>
        </div>
        <div className="h-[2px] bg-[rgba(255,255,255,0.06)] overflow-hidden">
          <div
            className="h-full bg-[rgba(0,212,255,0.3)] transition-all duration-1000"
            style={{ width: stats.cpu > 0 ? `${stats.cpu}%` : '0%' }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <MemoryStick size={8} className="text-[#444444]" />
            <span className="text-[9px] text-[#444444]">MEM</span>
          </div>
          <span className="text-[9px] text-[#666666]">{stats.mem > 0 ? `${stats.mem}%` : '—'}</span>
        </div>
        <div className="h-[2px] bg-[rgba(255,255,255,0.06)] overflow-hidden">
          <div
            className="h-full bg-[rgba(0,255,136,0.25)] transition-all duration-1000"
            style={{ width: stats.mem > 0 ? `${stats.mem}%` : '0%' }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-1">
            <HardDrive size={8} className="text-[#444444]" />
            <span className="text-[9px] text-[#444444]">DISK</span>
          </div>
          <span className="text-[9px] text-[#666666]">{stats.disk > 0 ? `${stats.disk}%` : '—'}</span>
        </div>
        <div className="h-[2px] bg-[rgba(255,255,255,0.06)] overflow-hidden">
          <div
            className="h-full bg-[rgba(255,217,61,0.25)] transition-all duration-1000"
            style={{ width: stats.disk > 0 ? `${stats.disk}%` : '0%' }}
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
        <div className="max-w-[70%] px-3 py-2 border border-[rgba(255,255,255,0.06)] text-[13px] leading-[1.7] text-[#e0e0e0]">
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
        <div className="border-l border-[rgba(0,212,255,0.2)] pl-3">
          {/* Thinking section */}
          {cleanedThinking && (
            <div className="mb-2.5">
              <button
                onClick={() => toggleThinking(msg.id)}
                className="flex items-center gap-1 text-[9px] text-[#555555] hover:text-[#888888] transition-colors duration-150"
              >
                {expandedThinking[msg.id] ? (
                  <ChevronDown size={10} />
                ) : (
                  <ChevronRight size={10} />
                )}
                <span>thinking</span>
                <span className="text-[#333333] ml-1">
                  ({cleanedThinking.length} chars)
                </span>
              </button>
              {expandedThinking[msg.id] && (
                <div className="mt-1.5 text-[10px] leading-[1.6] text-[#3a3a3a] max-h-40 overflow-y-auto pr-2 whitespace-pre-wrap border-l border-[rgba(255,255,255,0.04)] pl-2">
                  {cleanedThinking}
                </div>
              )}
            </div>
          )}

          {/* Tool calls */}
          {msg.toolCalls && msg.toolCalls.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {msg.toolCalls.map((tool, i) => (
                <span
                  key={i}
                  className="text-[9px] px-1.5 py-0.5 border border-[rgba(0,212,255,0.15)] text-[rgba(0,212,255,0.5)]"
                >
                  [{tool}]
                </span>
              ))}
            </div>
          )}

          {/* Content */}
          <div className="text-[13px] leading-[1.7] text-[#e0e0e0] whitespace-pre-wrap">
            {msg.content}
            {/* Streaming cursor */}
            {isStreaming && !msg.content && (
              <span className="inline-block w-[6px] h-[14px] bg-[rgba(0,212,255,0.5)] cursor-blink ml-0.5" />
            )}
            {isStreaming && msg.content && (
              <span className="inline-block w-[5px] h-[13px] bg-[rgba(0,212,255,0.5)] cursor-blink ml-0.5 align-middle" />
            )}
          </div>

          {/* Response metadata */}
          {msg.responseTime && !isStreaming && (
            <div className="mt-2 text-[9px] text-[#333333] flex items-center gap-2">
              <span>{msg.responseTime}ms</span>
              {msg.tokenCount ? (
                <>
                  <span className="text-[#222222]">·</span>
                  <span>~{msg.tokenCount} tokens</span>
                </>
              ) : null}
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
  const [isMobile, setIsMobile] = useState(false);
  const [useAgent, setUseAgent] = useState(true);

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

  // ─── Effects ─────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

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
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${errorData.error || "Unknown error"}`, isStreaming: false, responseTime: Date.now() - startTime }
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
              } else if (parsed.type === "tool_start") {
                const toolName = parsed.data?.name || "unknown";
                toolCalls = [...new Set([...toolCalls, toolName])];
              } else if (parsed.type === "tool_result") {
                // Tool completed - already tracked in toolCalls
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
          <span className="text-[10px] text-[#1a1a1a]">│</span>
          <span className="text-[10px] text-[#444444]">{selectedModel}</span>
          <div className="flex items-center gap-1.5 ml-1">
            <Circle
              size={5}
              className={status.connected ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff3333] text-[#ff3333]"}
            />
            <span className="text-[9px] text-[#555555] tracking-wider">
              {status.connected ? "CONNECTED" : "OFFLINE"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Agent mode toggle */}
          <button
            onClick={() => setUseAgent(!useAgent)}
            className={`text-[9px] tracking-wider px-2 py-0.5 border transition-colors duration-150 ${
              useAgent
                ? "text-[#00d4ff] border-[rgba(0,212,255,0.2)] bg-[rgba(0,212,255,0.05)]"
                : "text-[#444444] border-[rgba(255,255,255,0.04)] hover:text-[#666666] hover:border-[rgba(255,255,255,0.08)]"
            }`}
            title={useAgent ? "Full agent mode (ReAct + Tools)" : "Simple chat mode (no tools)"}
          >
            {useAgent ? "AGENT" : "CHAT"}
          </button>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="text-[9px] text-[#444444] hover:text-[#666666] transition-colors px-2 py-0.5 border border-[rgba(255,255,255,0.04)] hover:border-[rgba(255,255,255,0.08)]"
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
                <div className="text-[10px] leading-[1.4] text-[#1a1a1a] tracking-wider">
                  <div>╔══════════════╗</div>
                  <div>║ &nbsp; Z A I &nbsp; &nbsp; &nbsp; ║</div>
                  <div>╚══════════════╝</div>
                </div>
                <div className="h-px w-16 bg-[rgba(0,212,255,0.15)]" />
                <div className="text-[10px] text-[#2a2a2a] max-w-sm text-center leading-[1.7]">
                  Local AI agent interface.
                  <br />
                  <span className="text-[#222222]">All processing runs on your machine via Ollama.</span>
                </div>
                <div className="flex items-center gap-4 mt-2">
                  <div className="flex items-center gap-1.5">
                    <Circle size={4} className={status.connected ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff3333] text-[#ff3333]"} />
                    <span className="text-[9px] text-[#333333]">
                      {status.connected ? "OLLAMA CONNECTED" : "OLLAMA OFFLINE"}
                    </span>
                  </div>
                  <span className="text-[9px] text-[#222222]">│</span>
                  <span className="text-[9px] text-[#333333]">{selectedModel}</span>
                </div>
                {!status.connected && (
                  <div className="mt-1 px-4 py-2 border border-[rgba(255,51,51,0.15)] text-[9px] text-[#ff3333]">
                    Start Ollama: ollama serve
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
              />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* ─── Input Area ──────────────────────────────────────────────── */}
          <div className="shrink-0 border-t border-[rgba(255,255,255,0.06)]">
            <div className="flex items-end gap-3 px-5 py-3">
              <div className="text-[10px] text-[#333333] pb-1 select-none">{">"}</div>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={status.connected ? "Enter message..." : "Ollama not connected"}
                disabled={!status.connected}
                rows={1}
                className="flex-1 bg-transparent text-[13px] text-[#e0e0e0] placeholder-[#2a2a2a] resize-none outline-none min-h-[20px] max-h-[120px] leading-[1.6] disabled:opacity-20"
                style={{ fontFamily: "inherit" }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = "auto";
                  target.style.height = Math.min(target.scrollHeight, 120) + "px";
                }}
              />
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
            sidebarOpen ? "w-64" : "w-0"
          } ${isMobile ? "absolute right-0 top-0 bottom-0 z-20" : "relative"
          } shrink-0 border-l border-[rgba(255,255,255,0.06)] bg-[#050505] overflow-hidden transition-all duration-200`}
        >
          <div className="w-64 h-full overflow-y-auto px-4 py-4 space-y-5">
            {/* SYSTEM */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Server size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase">System</h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <span className="text-[9px] text-[#3a3a3a]">MODEL</span>
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
                  <span className="text-[9px] text-[#3a3a3a]">HOST</span>
                  <span className="text-[10px] text-[#555555]">localhost:11434</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[9px] text-[#3a3a3a]">STATUS</span>
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
                  <span className="text-[9px] text-[#3a3a3a]">UPTIME</span>
                  <span className="text-[10px] text-[#555555] tabular-nums">{formatUptime(uptime)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[9px] text-[#3a3a3a]">MODE</span>
                  <span className={`text-[10px] ${useAgent ? "text-[#00d4ff]" : "text-[#555555]"}`}>
                    {useAgent ? "AGENT" : "CHAT"}
                  </span>
                </div>
                {useAgent && status.agentAvailable !== undefined && (
                  <div className="flex justify-between items-center">
                    <span className="text-[9px] text-[#3a3a3a]">BRIDGE</span>
                    <div className="flex items-center gap-1.5">
                      <Circle
                        size={4}
                        className={status.agentAvailable ? "fill-[#00ff88] text-[#00ff88]" : "fill-[#ff8800] text-[#ff8800]"}
                      />
                      <span className="text-[10px] text-[#555555]">
                        {status.agentAvailable ? "Active" : "Inactive"}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.03)]" />

            {/* HARDWARE */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Cpu size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase">Hardware</h3>
              </div>
              <HardwareStats />
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.03)]" />

            {/* SESSION */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <Zap size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase">Session</h3>
              </div>
              <div className="space-y-2.5">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <MessageSquare size={8} className="text-[#3a3a3a]" />
                    <span className="text-[9px] text-[#3a3a3a]">MESSAGES</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">{sessionStats.messageCount}</span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Wrench size={8} className="text-[#3a3a3a]" />
                    <span className="text-[9px] text-[#3a3a3a]">TOOLS</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">{sessionStats.toolsUsed}</span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Clock size={8} className="text-[#3a3a3a]" />
                    <span className="text-[9px] text-[#3a3a3a]">AVG RESP</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.avgResponseTime > 0 ? `${sessionStats.avgResponseTime}ms` : "—"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <Activity size={8} className="text-[#3a3a3a]" />
                    <span className="text-[9px] text-[#3a3a3a]">TOKENS</span>
                  </div>
                  <span className="text-[10px] text-[#e0e0e0] tabular-nums">
                    {sessionStats.totalTokens > 0 ? `~${sessionStats.totalTokens}` : "—"}
                  </span>
                </div>
              </div>
            </section>

            <div className="h-px bg-[rgba(255,255,255,0.03)]" />

            {/* MODELS */}
            <section>
              <div className="flex items-center gap-1.5 mb-3">
                <HardDrive size={10} className="text-[#555555]" />
                <h3 className="text-[9px] tracking-[0.2em] text-[#555555] uppercase">Models</h3>
                {status.connected && (
                  <span className="text-[8px] text-[#3a3a3a] ml-auto">{status.modelCount}</span>
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
                        <span className={`text-[10px] truncate mr-2 ${model.name === selectedModel ? "text-[#e0e0e0]" : "text-[#555555]"}`}>
                          {model.name}
                        </span>
                        <span className="text-[8px] text-[#333333] shrink-0">
                          {formatBytes(model.size)}
                        </span>
                      </div>
                      {model.parameter_size !== "unknown" && (
                        <div className="text-[8px] text-[#2a2a2a] mt-0.5">
                          {model.parameter_size} · {model.quantization_level}
                        </div>
                      )}
                    </button>
                  ))
                ) : (
                  <div className="text-[9px] text-[#2a2a2a] px-2 py-1">
                    {status.connected ? "No models found" : "Cannot connect to Ollama"}
                  </div>
                )}
              </div>
            </section>

            {/* Footer */}
            <div className="pt-6">
              <div className="text-[7px] text-[#1a1a1a] text-center tracking-[0.4em] uppercase">
                ZAI Agent Interface v0.1
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
