import { NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

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

  return NextResponse.json({
    status: "degraded",
    agent: "AgentLocal",
    version: "0.2.0",
    bridge: false,
    ollama: false,
    hint: "Start bridge: python bridge_api.py (port 8000)",
  });
}
