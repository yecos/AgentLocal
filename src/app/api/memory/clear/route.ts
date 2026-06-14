import { NextResponse } from "next/server";

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

export async function POST() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/memory/clear`, {
      method: "POST",
      headers: bridgeHeaders(true),
      signal: AbortSignal.timeout(10000),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: "Bridge error" }));
      return NextResponse.json(
        { error: errorData.detail || `Bridge returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}
