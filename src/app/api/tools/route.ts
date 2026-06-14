import { NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";

/** Build headers for bridge requests, including Authorization if BRIDGE_TOKEN is set (B6 fix) */
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
    const response = await fetch(`${BRIDGE_BASE}/api/tools`, {
      headers: bridgeHeaders(),
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Bridge returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") || message.includes("fetch failed") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}
