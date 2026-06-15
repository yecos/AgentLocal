import { NextRequest, NextResponse } from "next/server";
import { BRIDGE_BASE, bridgeHeaders } from "@/lib/bridge";
import { sanitizeFilename } from "@/lib/bridge";

// D13 fix: Server-side file type validation to prevent dangerous uploads via API
const BLOCKED_EXTENSIONS = [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".scr", ".com", ".wsf", ".hta", ".cpl", ".inf", ".reg"];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB per file

export async function POST(request: NextRequest) {
  try {
    // Forward the multipart/form-data to the bridge
    const formData = await request.formData();

    // D13 fix: Validate files server-side before forwarding to bridge
    const files = formData.getAll("files");
    for (const file of files) {
      if (!(file instanceof File)) continue;
      const ext = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
      if (BLOCKED_EXTENSIONS.includes(ext)) {
        return NextResponse.json(
          { error: `File type "${ext}" is not allowed for security reasons` },
          { status: 400 }
        );
      }
      if (file.size > MAX_FILE_SIZE) {
        return NextResponse.json(
          { error: `File "${sanitizeFilename(file.name)}" exceeds 50 MB limit` },
          { status: 400 }
        );
      }
    }

    const bridgeRes = await fetch(`${BRIDGE_BASE}/api/upload`, {
      method: "POST",
      headers: bridgeHeaders(),
      body: formData,
      signal: AbortSignal.timeout(30000),
    });

    if (!bridgeRes.ok) {
      const errorData = await bridgeRes.json().catch(() => ({ detail: "Bridge upload error" }));
      return NextResponse.json(
        { error: errorData.detail || `Bridge returned ${bridgeRes.status}` },
        { status: bridgeRes.status }
      );
    }

    const data = await bridgeRes.json();
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message.includes("ECONNREFUSED") || message.includes("fetch failed") ? "Bridge not running" : message },
      { status: 503 }
    );
  }
}
