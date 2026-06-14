import { NextRequest, NextResponse } from "next/server";

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

export async function POST(request: NextRequest) {
  try {
    // Forward the multipart/form-data to the bridge
    const formData = await request.formData();

    const bridgeRes = await fetch(`${BRIDGE_BASE}/api/upload`, {
      method: "POST",
      headers: bridgeHeaders(),
      body: formData,
      signal: AbortSignal.timeout(30000),
    });

    if (!bridgeRes.ok) {
      const errorData = await bridgeRes.json().catch(() => ({ detail: "Bridge upload error" }));
      return NextResponse.json(
        { error: errorData.detail || `Bridge returned ${bridgeRes.status}` },
        { status: bridgeRes.status }
      );
    }

    const data = await bridgeRes.json();
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") || message.includes("fetch failed") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}
