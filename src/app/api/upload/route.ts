import { NextRequest, NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const files = formData.getAll("files");

    if (!files || files.length === 0) {
      return NextResponse.json(
        { error: "No files provided" },
        { status: 400 }
      );
    }

    // Forward to bridge
    const bridgeFormData = new FormData();
    for (const file of files) {
      if (file instanceof Blob) {
        bridgeFormData.append("files", file);
      }
    }

    const bridgeResponse = await fetch(`${BRIDGE_BASE}/api/upload`, {
      method: "POST",
      body: bridgeFormData,
      signal: AbortSignal.timeout(30000),
    });

    if (!bridgeResponse.ok) {
      const errorData = await bridgeResponse.json().catch(() => ({ detail: "Bridge error" }));
      return NextResponse.json(
        { error: errorData.detail || `Bridge returned ${bridgeResponse.status}` },
        { status: bridgeResponse.status }
      );
    }

    const data = await bridgeResponse.json();
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    if (message.includes("ECONNREFUSED") || message.includes("fetch failed")) {
      return NextResponse.json(
        { error: "Bridge not running. Start: python bridge_api.py" },
        { status: 503 }
      );
    }
    return NextResponse.json(
      { error: message },
      { status: 500 }
    );
  }
}
