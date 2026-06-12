import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/memory - Search memory entries (by type, category, or keyword)
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const type = searchParams.get('type')
    const category = searchParams.get('category')
    const keyword = searchParams.get('keyword')
    const limit = parseInt(searchParams.get('limit') || '50')
    const offset = parseInt(searchParams.get('offset') || '0')

    const where: Record<string, unknown> = {}
    if (type) where.type = type
    if (category) where.category = category
    if (keyword) where.content = { contains: keyword }

    const entries = await prisma.memoryEntry.findMany({
      where,
      orderBy: { createdAt: 'desc' },
      take: limit,
      skip: offset,
    })

    const total = await prisma.memoryEntry.count({ where })

    return NextResponse.json({ entries, total })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/memory - Add a memory entry
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { type, category, content, context, confidence, source, tags, expiresAt } = body

    if (!type || typeof type !== 'string') {
      return NextResponse.json(
        { error: 'type is required and must be a string' },
        { status: 400 }
      )
    }

    if (!content || typeof content !== 'string') {
      return NextResponse.json(
        { error: 'content is required and must be a string' },
        { status: 400 }
      )
    }

    const entry = await prisma.memoryEntry.create({
      data: {
        type,
        category: category || null,
        content,
        context: context || null,
        confidence: confidence ?? 1.0,
        source: source || null,
        tags: tags || null,
        expiresAt: expiresAt ? new Date(expiresAt) : null,
      },
    })

    return NextResponse.json(entry, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/memory - Delete old/expired entries
export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const expiredOnly = searchParams.get('expiredOnly') === 'true'
    const id = searchParams.get('id')

    if (id) {
      const entry = await prisma.memoryEntry.findUnique({ where: { id } })
      if (!entry) {
        return NextResponse.json({ error: 'Entry not found' }, { status: 404 })
      }
      await prisma.memoryEntry.delete({ where: { id } })
      return NextResponse.json({ success: true, deleted: 1 })
    }

    if (expiredOnly) {
      const result = await prisma.memoryEntry.deleteMany({
        where: {
          expiresAt: { not: null, lt: new Date() },
        },
      })
      return NextResponse.json({ success: true, deleted: result.count })
    }

    return NextResponse.json(
      { error: 'Provide id or expiredOnly=true parameter' },
      { status: 400 }
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
