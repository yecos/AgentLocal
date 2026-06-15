import { NextRequest, NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await fetch(`${BRIDGE_BASE}/api/memory/save`, {
      method: "POST",
      headers: bridgeHeaders(true),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 503 });
  }
}
