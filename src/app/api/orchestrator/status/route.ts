import { NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

export async function GET() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/orchestrator/status`, {
      headers: bridgeHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { available: false, error: message.includes("ECONNREFUSED") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { task, agents } = body;

    if (!task || typeof task !== "string") {
      return NextResponse.json(
        { error: "task is required and must be a string" },
        { status: 400 }
      );
    }

    const response = await fetch(`${BRIDGE_BASE}/api/orchestrator/run`, {
      method: "POST",
      headers: bridgeHeaders(true),
      body: JSON.stringify({ task, agents: agents || [] }),
      signal: AbortSignal.timeout(60000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 503 });
  }
}
