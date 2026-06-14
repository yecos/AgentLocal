import { NextRequest, NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";

function bridgeHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = process.env.BRIDGE_TOKEN;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { tool_name, arguments: toolArgs } = body;

    if (!tool_name || typeof tool_name !== "string") {
      return NextResponse.json(
        { error: "tool_name is required and must be a string" },
        { status: 400 }
      );
    }

    const response = await fetch(`${BRIDGE_BASE}/api/execute`, {
      method: "POST",
      headers: bridgeHeaders(),
      body: JSON.stringify({ tool_name, arguments: toolArgs || {} }),
      signal: AbortSignal.timeout(30000),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    if (message.includes("ECONNREFUSED") || message.includes("fetch failed")) {
      return NextResponse.json(
        { error: "Bridge not running. Start: python bridge_api.py" },
        { status: 503 }
      );
    }
    return NextResponse.json({ error: message }, { status: 503 });
  }
}
