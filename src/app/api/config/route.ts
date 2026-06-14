import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/config - Get all config values (also merges with bridge config)
export async function GET() {
  try {
    const configs = await prisma.agentConfig.findMany({
      orderBy: { key: 'asc' },
    })

    // Also try to get bridge config for a unified view
    let bridgeConfig = null;
    try {
      const token = process.env.BRIDGE_TOKEN;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const bridgeRes = await fetch("http://localhost:8000/api/config", {
        headers,
        signal: AbortSignal.timeout(3000),
      });
      if (bridgeRes.ok) bridgeConfig = await bridgeRes.json();
    } catch { /* bridge not available */ }

    return NextResponse.json({ configs, bridgeConfig })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/config - Set a config value
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { key, value, category } = body

    if (!key || typeof key !== 'string') {
      return NextResponse.json(
        { error: 'key is required and must be a string' },
        { status: 400 }
      )
    }

    if (value === undefined || value === null) {
      return NextResponse.json(
        { error: 'value is required' },
        { status: 400 }
      )
    }

    const config = await prisma.agentConfig.upsert({
      where: { key },
      update: { value: String(value), category: category || 'general' },
      create: { key, value: String(value), category: category || 'general' },
    })

    return NextResponse.json(config, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/config - Delete a config value
export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const key = searchParams.get('key')

    if (!key) {
      return NextResponse.json(
        { error: 'key query parameter is required' },
        { status: 400 }
      )
    }

    const existing = await prisma.agentConfig.findUnique({ where: { key } })
    if (!existing) {
      return NextResponse.json({ error: 'Config not found' }, { status: 404 })
    }

    await prisma.agentConfig.delete({ where: { key } })

    return NextResponse.json({ success: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
