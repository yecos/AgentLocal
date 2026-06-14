import { NextRequest, NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { model } = body;

    if (!model || typeof model !== "string") {
      return NextResponse.json(
        { error: "model is required and must be a string" },
        { status: 400 }
      );
    }

    // Try bridge first
    try {
      const bridgeRes = await fetch(`${BRIDGE_BASE}/api/models/switch`, {
        method: "POST",
        headers: bridgeHeaders(true),
        body: JSON.stringify({ model }),
        signal: AbortSignal.timeout(5000),
      });
      if (bridgeRes.ok) {
        const data = await bridgeRes.json();
        return NextResponse.json(data);
      }
    } catch {
      // Bridge not available - fall through to local response
    }

    // If bridge is not available, just return success (model switch is local)
    return NextResponse.json({ success: true, model, source: "local" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
