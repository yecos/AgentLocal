import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/conversations/[id]/messages - Get messages (paginated, cursor-based)
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const limit = Math.max(1, parseInt(searchParams.get('limit') || '50') || 50)
    const cursor = searchParams.get('cursor')

    const conversation = await prisma.conversation.findUnique({ where: { id } })
    if (!conversation) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 })
    }

    const messages = await prisma.conversationMessage.findMany({
      where: { conversationId: id },
      orderBy: { createdAt: 'asc' },
      take: limit + 1,
      ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
    })

    const hasMore = messages.length > limit
    const items = hasMore ? messages.slice(0, -1) : messages
    const nextCursor = hasMore ? items[items.length - 1]?.id : null

    return NextResponse.json({ messages: items, nextCursor, hasMore })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/conversations/[id]/messages - Add a message to a conversation
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()
    const { role, content, thinking, toolCalls, tokenCount, responseTime } = body

    if (!role || typeof role !== 'string') {
      return NextResponse.json(
        { error: 'role is required and must be a string' },
        { status: 400 }
      )
    }

    if (!content || typeof content !== 'string') {
      return NextResponse.json(
        { error: 'content is required and must be a string' },
        { status: 400 }
      )
    }

    const conversation = await prisma.conversation.findUnique({ where: { id } })
    if (!conversation) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 })
    }

    const message = await prisma.conversationMessage.create({
      data: {
        conversationId: id,
        role,
        content,
        thinking: thinking || null,
        toolCalls: toolCalls ? JSON.stringify(toolCalls) : null,
        tokenCount: tokenCount || 0,
        responseTime: responseTime || null,
      },
    })

    return NextResponse.json(message, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
