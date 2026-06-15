import { NextRequest } from "next/server";
import { BRIDGE_BASE, OLLAMA_BASE, bridgeHeaders } from "@/lib/bridge";

/**
 * Internal agent JSON keys that should be filtered from the stream.
 * These are Spanish-language ReAct framework keys used by the Python agent.
 * R12 fix: Only match when these appear as JSON keys (preceded by { or ,)
 */
const INTERNAL_JSON_KEYS = ['"pensamiento"', '"accion"', '"respuesta_final"', '"params"'];
// R12 fix: More precise regex — only match JSON key patterns inside objects
const INTERNAL_JSON_REGEX = /(?<=[{,])\s*"(?:pensamiento|accion|respuesta_final|params)"\s*:\s*"[^"]*"\s*,?\s*/g;
const INTERNAL_JSON_KEY_REGEX = /"(?:pensamiento|accion|respuesta_final|params)"\s*:/g;

/**
 * Filter internal agent JSON from text content.
 * Prevents ReAct framework internals from leaking to the user.
 */
function filterInternalJson(content: string): string {
  const trimmed = content.trim();
  // Try parsing as JSON to extract the final response
  if (trimmed.startsWith('{')) {
    try {
      const jsonObj = JSON.parse(trimmed);
      const extracted = jsonObj.respuesta_final || jsonObj.pensamiento || '';
      if (extracted) return extracted;
    } catch {
      // Not valid JSON - check for internal key patterns
      if (INTERNAL_JSON_KEYS.some(k => trimmed.includes(k))) {
        return ''; // Skip this chunk entirely
      }
    }
  }
  // Strip remaining internal keys from text
  let filtered = content.replace(INTERNAL_JSON_REGEX, '');
  filtered = filtered.replace(INTERNAL_JSON_KEY_REGEX, '');
  return filtered.trim();
}

/**
 * Filter error messages to hide internal agent JSON keys.
 */
function filterErrorMessage(errMsg: string): string {
  if (INTERNAL_JSON_KEYS.some(k => errMsg.includes(k))) {
    return 'Error processing model response';
  }
  return errMsg;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, model, useAgent } = body;

    // If useAgent is true, route to the Python bridge (full ReAct agent)
    if (useAgent) {
      const bridgeResult = await streamFromBridge(messages, model);
      // D1 fix: If bridge returns a 503 (not running), auto-fallback to Ollama
      if (bridgeResult.status === 503) {
        try {
          const errorData = await bridgeResult.clone().json().catch(() => ({}));
          if (errorData.bridgeRequired) {
            // Attempt Ollama fallback with a warning event prepended
            return await streamFromOllamaWithWarning(
              messages,
              model,
              "Bridge not available — using simple chat mode (no tools). Start bridge: python bridge_api.py"
            );
          }
        } catch {
          // Cannot parse error, return original bridge error
        }
      }
      return bridgeResult;
    }

    // Otherwise, use Ollama directly (simple chat, no tools)
    return await streamFromOllama(messages, model);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    if (message.includes("ECONNREFUSED") || message.includes("fetch failed")) {
      return new Response(
        JSON.stringify({
          error: "Service not running",
          details: "Cannot connect. Please start Ollama or the Agent Bridge.",
        }),
        { status: 503, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(
      JSON.stringify({ error: message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function streamFromBridge(messages: Array<{role: string; content: string}>, model: string) {
  const lastUserMsg = messages.filter(m => m.role === "user").pop();
  if (!lastUserMsg) {
    return new Response(
      JSON.stringify({ error: "No user message found" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  try {
    const bridgeResponse = await fetch(`${BRIDGE_BASE}/api/chat`, {
      method: "POST",
      headers: bridgeHeaders(true),
      body: JSON.stringify({
        message: lastUserMsg.content,
        model: model,
        stream: true,
      }),
    });

    if (!bridgeResponse.ok) {
      const errorData = await bridgeResponse.json().catch(() => ({ detail: "Bridge error" }));
      return new Response(
        JSON.stringify({
          error: "Agent Bridge error",
          details: filterErrorMessage(errorData.detail || `Bridge returned ${bridgeResponse.status}`),
          bridgeRequired: true,
        }),
        { status: bridgeResponse.status, headers: { "Content-Type": "application/json" } }
      );
    }

    // D2 fix: Forward the SSE stream from the bridge WITH server-side JSON filtering
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        const reader = bridgeResponse.body?.getReader();
        if (!reader) {
          controller.close();
          return;
        }

        const decoder = new TextDecoder();
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            // Filter internal JSON from bridge SSE events before forwarding to client
            const lines = chunk.split("\n");
            const filteredLines: string[] = [];
            let sawDone = false; // R2 fix: track [DONE] to avoid duplicates
            for (const line of lines) {
              if (!line.startsWith("data: ")) {
                filteredLines.push(line);
                continue;
              }
              const data = line.slice(6);
              if (data === "[DONE]") {
                sawDone = true;
                continue; // R2 fix: skip bridge's [DONE], we'll add our own at the end
              }
              try {
                const parsed = JSON.parse(data);
                // Filter text events for internal agent JSON
                if (parsed.type === "text" && parsed.data) {
                  const filtered = filterInternalJson(parsed.data);
                  if (filtered) {
                    parsed.data = filtered;
                    filteredLines.push(`data: ${JSON.stringify(parsed)}`);
                  }
                  // Skip empty results (filtered out internal JSON)
                } else if (parsed.type === "error") {
                  parsed.data = filterErrorMessage(String(parsed.data || ''));
                  filteredLines.push(`data: ${JSON.stringify(parsed)}`);
                } else {
                  filteredLines.push(line);
                }
              } catch {
                filteredLines.push(line);
              }
            }
            controller.enqueue(encoder.encode(filteredLines.join("\n")));
          }
          controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        } catch (error) {
          const errMsg = error instanceof Error ? error.message : "Stream error";
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ type: "error", data: errMsg })}\n\n`)
          );
        } finally {
          controller.close();
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch {
    return new Response(
      JSON.stringify({
        error: "Agent Bridge not running",
        details: "Start the bridge first: python bridge_api.py (port 8000)",
        bridgeRequired: true,
      }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function streamFromOllama(messages: Array<{role: string; content: string}>, model: string) {
  const ollamaResponse = await fetch(`${OLLAMA_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages,
      stream: true,
    }),
  });

  if (!ollamaResponse.ok) {
    const errorText = await ollamaResponse.text();
    return new Response(
      JSON.stringify({
        error: `Ollama error: ${ollamaResponse.status}`,
        details: errorText,
      }),
      { status: ollamaResponse.status, headers: { "Content-Type": "application/json" } }
    );
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const reader = ollamaResponse.body?.getReader();
      if (!reader) {
        controller.close();
        return;
      }

      const decoder = new TextDecoder();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n").filter((line: string) => line.trim());

          for (const line of lines) {
            try {
              const parsed = JSON.parse(line);
              let content = parsed.message?.content || "";
              // D2 fix: Filter internal agent JSON on the server side too
              if (content) {
                content = filterInternalJson(content);
              }
              const event = {
                type: "text",
                data: content,
              };
              if (content) {
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
              }
            } catch {
              // Skip malformed lines
            }
          }
        }
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      } catch (error) {
        const errMsg = error instanceof Error ? error.message : "Stream error";
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "error", data: errMsg })}\n\n`)
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

/**
 * D1 fix: Stream from Ollama with a warning event prepended.
 * Used as fallback when bridge is unavailable but agent mode was requested.
 */
async function streamFromOllamaWithWarning(
  messages: Array<{role: string; content: string}>,
  model: string,
  warning: string
) {
  const ollamaResponse = await fetch(`${OLLAMA_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages,
      stream: true,
    }),
  });

  if (!ollamaResponse.ok) {
    const errorText = await ollamaResponse.text();
    return new Response(
      JSON.stringify({
        error: `Ollama error: ${ollamaResponse.status}`,
        details: errorText,
      }),
      { status: ollamaResponse.status, headers: { "Content-Type": "application/json" } }
    );
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      // Prepend warning event
      controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "warning", data: warning })}\n\n`));

      const reader = ollamaResponse.body?.getReader();
      if (!reader) {
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
        return;
      }

      const decoder = new TextDecoder();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n").filter((line: string) => line.trim());

          for (const line of lines) {
            try {
              const parsed = JSON.parse(line);
              let content = parsed.message?.content || "";
              if (content) {
                content = filterInternalJson(content);
              }
              const event = { type: "text", data: content };
              if (content) {
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
              }
            } catch {
              // Skip malformed lines
            }
          }
        }
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      } catch (error) {
        const errMsg = error instanceof Error ? error.message : "Stream error";
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "error", data: errMsg })}\n\n`)
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
