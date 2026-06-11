import { NextRequest } from "next/server";

const OLLAMA_BASE = "http://localhost:11434";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, model } = body;

    if (!messages || !model) {
      return new Response(
        JSON.stringify({ error: "Missing messages or model" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

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

    // Stream the NDJSON response from Ollama
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
                // Forward the Ollama response chunks
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(parsed)}\n\n`));
              } catch {
                // Skip malformed lines
              }
            }
          }
          controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        } catch (error) {
          const errMsg = error instanceof Error ? error.message : "Stream error";
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ error: errMsg })}\n\n`)
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
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    // Check if it's a connection refused error
    if (message.includes("ECONNREFUSED") || message.includes("fetch failed")) {
      return new Response(
        JSON.stringify({
          error: "Ollama is not running",
          details: "Cannot connect to localhost:11434. Please start Ollama first.",
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
