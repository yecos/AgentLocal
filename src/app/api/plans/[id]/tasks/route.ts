import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/plans/[id]/tasks - Get tasks for a plan
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status')

    const plan = await prisma.executionPlan.findUnique({ where: { id } })
    if (!plan) {
      return NextResponse.json({ error: 'Plan not found' }, { status: 404 })
    }

    const where: Record<string, unknown> = { planId: id }
    if (status) where.status = status

    const tasks = await prisma.task.findMany({
      where,
      orderBy: { createdAt: 'asc' },
    })

    return NextResponse.json({ tasks })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/plans/[id]/tasks - Add a task to a plan
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()
    const { title, description, priority, dependencies, parentId } = body

    if (!title || typeof title !== 'string') {
      return NextResponse.json(
        { error: 'title is required and must be a string' },
        { status: 400 }
      )
    }

    const plan = await prisma.executionPlan.findUnique({ where: { id } })
    if (!plan) {
      return NextResponse.json({ error: 'Plan not found' }, { status: 404 })
    }

    const task = await prisma.task.create({
      data: {
        planId: id,
        title,
        description: description || null,
        priority: priority || 'medium',
        dependencies: dependencies || null,
        parentId: parentId || null,
      },
    })

    return NextResponse.json(task, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
