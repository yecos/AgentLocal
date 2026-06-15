import { NextResponse } from "next/server";
import { OLLAMA_BASE } from "@/lib/bridge";

export async function GET() {
  try {
    const response = await fetch(`${OLLAMA_BASE}/api/tags`, {
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Ollama returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    const models = (data.models || []).map((m: { name: string; size: number; modified_at: string; details?: { family?: string; parameter_size?: string; quantization_level?: string } }) => ({
      name: m.name,
      size: m.size,
      modified_at: m.modified_at,
      family: m.details?.family || "unknown",
      parameter_size: m.details?.parameter_size || "unknown",
      quantization_level: m.details?.quantization_level || "unknown",
    }));

    return NextResponse.json({ models });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") || message.includes("fetch failed") ? "Ollama is not running" : message },
      { status: 503 }
    );
  }
}
