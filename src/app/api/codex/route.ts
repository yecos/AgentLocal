import { NextRequest, NextResponse } from "next/server";
import { codex, localRequest } from "@/lib/codex";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!localRequest(request)) return NextResponse.json({ error: "Acceso local requerido." }, { status: 403 });
  try {
    return NextResponse.json(await codex.status());
  } catch (error) {
    return NextResponse.json({ available: false, authenticated: false, models: [], approvals: [], error: error instanceof Error ? error.message : "Codex no está disponible." });
  }
}

export async function POST(request: NextRequest) {
  if (!localRequest(request)) return NextResponse.json({ error: "Acceso local requerido." }, { status: 403 });
  try {
    const body = await request.json();
    await codex.connect();
    if (body.action === "login") {
      const login = await codex.startLogin();
      return NextResponse.json({ authUrl: login.authUrl });
    }
    if (body.action === "cancelLogin") {
      await codex.cancelLogin();
      return NextResponse.json({ success: true });
    }
    if (body.action === "logout") {
      await codex.logout();
      return NextResponse.json({ success: true });
    }
    if (body.action === "approval" && typeof body.id === "string" && typeof body.allowed === "boolean") {
      codex.approve(body.id, body.allowed);
      return NextResponse.json({ success: true });
    }
    return NextResponse.json({ error: "Acción no válida." }, { status: 400 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Falló la conexión con Codex." }, { status: 400 });
  }
}
