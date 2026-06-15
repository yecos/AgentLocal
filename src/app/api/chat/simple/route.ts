import { NextRequest, NextResponse } from "next/server";
import { OLLAMA_BASE } from "@/lib/bridge";

/**
 * R12 fix: Internal JSON key filter for simple mode too.
 * Matches the same pattern used in the streaming chat route.
 */
const INTERNAL_JSON_KEYS = ['"pensamiento"', '"accion"', '"respuesta_final"', '"params"'];
const INTERNAL_JSON_REGEX = /(?<=[{,])\s*"(?:pensamiento|accion|respuesta_final|params)"\s*:\s*"[^"]*"\s*,?\s*/g;
const INTERNAL_JSON_KEY_REGEX = /"(?:pensamiento|accion|respuesta_final|params)"\s*:/g;

function filterInternalJson(content: string): string {
  const trimmed = content.trim();
  if (trimmed.startsWith('{')) {
    try {
      const jsonObj = JSON.parse(trimmed);
      const extracted = jsonObj.respuesta_final || jsonObj.pensamiento || '';
      if (extracted) return extracted;
    } catch {
      if (INTERNAL_JSON_KEYS.some(k => trimmed.includes(k))) {
        return '';
      }
    }
  }
  let filtered = content.replace(INTERNAL_JSON_REGEX, '');
  filtered = filtered.replace(INTERNAL_JSON_KEY_REGEX, '');
  return filtered.trim();
}

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
    // R19 fix: Filter internal agent JSON from simple mode responses too
    if (data.message?.content) {
      data.message.content = filterInternalJson(data.message.content);
    }
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") ? "Ollama not running" : message },
      { status: 503 }
    );
  }
}
