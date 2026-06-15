import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/notes - List notes
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const pinned = searchParams.get('pinned')
    const limit = Math.max(1, parseInt(searchParams.get('limit') || '50') || 50)

    const where: Record<string, unknown> = {}
    if (pinned !== null && pinned !== undefined) {
      where.pinned = pinned === 'true'
    }

    const notes = await prisma.note.findMany({
      where,
      orderBy: [{ pinned: 'desc' }, { updatedAt: 'desc' }],
      take: limit,
    })

    return NextResponse.json({ notes })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/notes - Create a note
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { title, content, pinned, tags } = body

    if (!title || typeof title !== 'string') {
      return NextResponse.json(
        { error: 'title is required and must be a string' },
        { status: 400 }
      )
    }

    if (!content || typeof content !== 'string') {
      return NextResponse.json(
        { error: 'content is required and must be a string' },
        { status: 400 }
      )
    }

    const note = await prisma.note.create({
      data: {
        title,
        content,
        pinned: pinned ?? false,
        tags: tags || null,
      },
    })

    return NextResponse.json(note, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// PATCH /api/notes - Update a note
export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json()
    const { id, title, content, pinned } = body

    if (!id) {
      return NextResponse.json(
        { error: 'id is required' },
        { status: 400 }
      )
    }

    const existing = await prisma.note.findUnique({ where: { id } })
    if (!existing) {
      return NextResponse.json({ error: 'Note not found' }, { status: 404 })
    }

    const data: Record<string, unknown> = {}
    if (title !== undefined) data.title = title
    if (content !== undefined) data.content = content
    if (pinned !== undefined) data.pinned = pinned

    const note = await prisma.note.update({
      where: { id },
      data,
    })

    return NextResponse.json(note)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/notes - Delete a note
export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const id = searchParams.get('id')

    if (!id) {
      return NextResponse.json(
        { error: 'id query parameter is required' },
        { status: 400 }
      )
    }

    const existing = await prisma.note.findUnique({ where: { id } })
    if (!existing) {
      return NextResponse.json({ error: 'Note not found' }, { status: 404 })
    }

    await prisma.note.delete({ where: { id } })

    return NextResponse.json({ success: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
