import { NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

export async function GET() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/circuit-breaker/status`, {
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
