import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/conversations - List all conversations with latest message
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status')
    const limit = parseInt(searchParams.get('limit') || '50')
    const offset = parseInt(searchParams.get('offset') || '0')

    const where = status ? { status } : { status: { not: 'deleted' } }

    const conversations = await prisma.conversation.findMany({
      where,
      orderBy: { updatedAt: 'desc' },
      take: limit,
      skip: offset,
      include: {
        messages: {
          orderBy: { createdAt: 'desc' },
          take: 1,
          select: { id: true, role: true, content: true, createdAt: true },
        },
        _count: { select: { messages: true } },
      },
    })

    const total = await prisma.conversation.count({ where })

    return NextResponse.json({ conversations, total })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/conversations - Create a new conversation
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { title, model, userId } = body

    if (!title || typeof title !== 'string') {
      return NextResponse.json(
        { error: 'title is required and must be a string' },
        { status: 400 }
      )
    }

    const conversation = await prisma.conversation.create({
      data: {
        title,
        model: model || null,
        userId: userId || null,
      },
    })

    return NextResponse.json(conversation, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
