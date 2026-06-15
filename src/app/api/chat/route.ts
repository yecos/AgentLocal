import { NextRequest } from "next/server";
import { BRIDGE_BASE, OLLAMA_BASE, bridgeHeaders } from "@/lib/bridge";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, model, useAgent } = body;

    // If useAgent is true, route to the Python bridge (full ReAct agent)
    if (useAgent) {
      return await streamFromBridge(messages, model);
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
          details: errorData.detail || `Bridge returned ${bridgeResponse.status}`,
          bridgeRequired: true,
        }),
        { status: bridgeResponse.status, headers: { "Content-Type": "application/json" } }
      );
    }

    // Forward the SSE stream from the bridge
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
            controller.enqueue(encoder.encode(chunk));
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
              const event = {
                type: "text",
                data: parsed.message?.content || "",
              };
              controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
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
