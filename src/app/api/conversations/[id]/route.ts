import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/conversations/[id] - Get conversation with messages
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params

    const conversation = await prisma.conversation.findUnique({
      where: { id },
      include: {
        messages: { orderBy: { createdAt: 'asc' } },
        user: { select: { id: true, name: true, email: true } },
      },
    })

    if (!conversation) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 })
    }

    return NextResponse.json(conversation)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// PATCH /api/conversations/[id] - Update conversation (title, status)
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()
    const { title, status } = body

    const existing = await prisma.conversation.findUnique({ where: { id } })
    if (!existing) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 })
    }

    const data: Record<string, unknown> = {}
    if (title !== undefined) data.title = title
    if (status !== undefined) data.status = status

    const conversation = await prisma.conversation.update({
      where: { id },
      data,
    })

    return NextResponse.json(conversation)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/conversations/[id] - Delete conversation
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params

    const existing = await prisma.conversation.findUnique({ where: { id } })
    if (!existing) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 })
    }

    await prisma.conversation.delete({ where: { id } })

    return NextResponse.json({ success: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
