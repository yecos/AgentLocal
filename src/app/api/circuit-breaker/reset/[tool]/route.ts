import { NextRequest, NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ tool: string }> }
) {
  try {
    const { tool } = await params;

    if (!tool) {
      return NextResponse.json(
        { error: "tool name is required" },
        { status: 400 }
      );
    }

    const response = await fetch(`${BRIDGE_BASE}/api/circuit-breaker/reset/${encodeURIComponent(tool)}`, {
      method: "POST",
      headers: bridgeHeaders(true),
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 503 });
  }
}
