import { NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";
const OLLAMA_BASE = "http://localhost:11434";

export async function GET() {
  // Try bridge first (has agent status + Ollama status)
  try {
    const bridgeResponse = await fetch(`${BRIDGE_BASE}/api/status`, {
      signal: AbortSignal.timeout(3000),
    });

    if (bridgeResponse.ok) {
      const data = await bridgeResponse.json();
      return NextResponse.json({
        connected: data.connected,
        agentAvailable: data.agent_available,
        models: data.models || [],
        modelCount: data.modelCount || 0,
        uptime: data.uptime || 0,
      });
    }
  } catch {
    // Bridge not available, fall back to direct Ollama check
  }

  // Direct Ollama check
  try {
    const response = await fetch(`${OLLAMA_BASE}/api/tags`, {
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      return NextResponse.json({
        connected: false,
        agentAvailable: false,
        models: [],
        modelCount: 0,
        error: `Ollama returned ${response.status}`,
      });
    }

    const data = await response.json();
    const models = (data.models || []).map((m: { name: string; size: number; modified_at: string; details?: { family?: string; parameter_size?: string; quantization_level?: string } }) => ({
      name: m.name,
      size: m.size,
      modified_at: m.modified_at,
      family: m.details?.family || "unknown",
      parameter_size: m.details?.parameter_size || "unknown",
      quantization_level: m.details?.quantization_level || "unknown",
    }));

    return NextResponse.json({
      connected: true,
      agentAvailable: false,
      models,
      modelCount: models.length,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({
      connected: false,
      agentAvailable: false,
      models: [],
      modelCount: 0,
      error: message.includes("ECONNREFUSED") || message.includes("fetch failed")
        ? "Ollama is not running"
        : message,
    });
  }
}
