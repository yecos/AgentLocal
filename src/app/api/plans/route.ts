import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/plans - List execution plans with task counts
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status')
    const limit = parseInt(searchParams.get('limit') || '50')
    const offset = parseInt(searchParams.get('offset') || '0')

    const where = status ? { status } : {}

    const plans = await prisma.executionPlan.findMany({
      where,
      orderBy: { updatedAt: 'desc' },
      take: limit,
      skip: offset,
      include: {
        _count: { select: { tasks: true } },
      },
    })

    const total = await prisma.executionPlan.count({ where })

    return NextResponse.json({ plans, total })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/plans - Create a new execution plan
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { goal, description, planType, userId } = body

    if (!goal || typeof goal !== 'string') {
      return NextResponse.json(
        { error: 'goal is required and must be a string' },
        { status: 400 }
      )
    }

    const plan = await prisma.executionPlan.create({
      data: {
        goal,
        description: description || null,
        planType: planType || 'script',
        userId: userId || null,
      },
    })

    return NextResponse.json(plan, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
