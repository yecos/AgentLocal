import { NextRequest, NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";

/** Build headers for bridge requests, including Authorization if BRIDGE_TOKEN is set (B6 fix) */
function bridgeHeaders(jsonContentType = false): Record<string, string> {
  const headers: Record<string, string> = {};
  if (jsonContentType) headers["Content-Type"] = "application/json";
  const token = process.env.BRIDGE_TOKEN;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function GET() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/plan`, {
      headers: bridgeHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { active: false, error: "Bridge not available" },
      { status: 503 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { goal, task_type, advance, result } = body;

    if (advance) {
      const response = await fetch(`${BRIDGE_BASE}/api/plan/advance`, {
        method: "POST",
        headers: bridgeHeaders(true),
        body: JSON.stringify({ result: result || "" }),
        signal: AbortSignal.timeout(10000),
      });
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    }

    if (!goal || typeof goal !== "string") {
      return NextResponse.json(
        { success: false, error: "goal is required and must be a string" },
        { status: 400 }
      );
    }

    const response = await fetch(`${BRIDGE_BASE}/api/plan`, {
      method: "POST",
      headers: bridgeHeaders(true),
      body: JSON.stringify({ goal, task_type: task_type || null }),
      signal: AbortSignal.timeout(10000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { success: false, error: message },
      { status: 503 }
    );
  }
}
