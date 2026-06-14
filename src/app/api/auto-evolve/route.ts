import { NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

// POST /api/auto-evolve - Trigger an auto-evolve cycle
export async function POST() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/auto-evolve`, {
      method: "POST",
      headers: bridgeHeaders(true),
      signal: AbortSignal.timeout(30000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 503 });
  }
}

// GET /api/auto-evolve - Get evolution log
export async function GET() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/auto-evolve/log`, {
      headers: bridgeHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { available: false, entries: [], error: message.includes("ECONNREFUSED") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}
