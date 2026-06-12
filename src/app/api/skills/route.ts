import { NextResponse } from "next/server";

const BRIDGE_BASE = "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/skills`, {
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Bridge not available", skills: [], loaded: false },
      { status: 503 }
    );
  }
}

export async function POST() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/skills/reload`, {
      method: "POST",
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
