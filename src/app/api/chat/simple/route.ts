import { NextRequest, NextResponse } from "next/server";
import { OLLAMA_BASE } from "@/lib/bridge";

/**
 * POST /api/chat/simple — Direct Ollama chat without agent/tools.
 * Used by the frontend when useAgent=false for simple conversations.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, model } = body;

    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json(
        { error: "messages array is required" },
        { status: 400 }
      );
    }

    const ollamaResponse = await fetch(`${OLLAMA_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: false }),
      signal: AbortSignal.timeout(60000),
    });

    if (!ollamaResponse.ok) {
      const errorText = await ollamaResponse.text();
      return NextResponse.json(
        { error: `Ollama error: ${ollamaResponse.status}`, details: errorText },
        { status: ollamaResponse.status }
      );
    }

    const data = await ollamaResponse.json();
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") ? "Ollama not running" : message },
      { status: 503 }
    );
  }
}
