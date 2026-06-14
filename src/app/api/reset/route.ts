import { NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";

export async function POST() {
  try {
    const response = await fetch(`${BRIDGE_BASE}/api/reset`, {
      method: "POST",
      headers: bridgeHeaders(true),
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
      { error: message.includes("ECONNREFUSED") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}
