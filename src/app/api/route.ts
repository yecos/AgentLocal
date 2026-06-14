import { NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";

/** Build headers for bridge requests, including Authorization if BRIDGE_TOKEN is set */
function bridgeHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = process.env.BRIDGE_TOKEN;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function GET() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/health`, {
      headers: bridgeHeaders(),
      signal: AbortSignal.timeout(3000),
    });

    if (response.ok) {
      const data = await response.json();
      return NextResponse.json({
        status: "online",
        agent: "AgentLocal",
        version: data.version || "unknown",
        bridge: true,
        ollama: data.ollama || false,
      });
    }
  } catch {
    // Bridge not reachable
  }

  // Fallback: return basic status
  return NextResponse.json({
    status: "degraded",
    agent: "AgentLocal",
    version: "0.2.0",
    bridge: false,
    ollama: false,
    hint: "Start bridge: python bridge_api.py (port 8000)",
  });
}
