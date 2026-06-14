import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/plans/[id] - Get plan with tasks
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params

    const plan = await prisma.executionPlan.findUnique({
      where: { id },
      include: {
        tasks: { orderBy: { order: 'asc' } },
      },
    })

    if (!plan) {
      return NextResponse.json({ error: 'Plan not found' }, { status: 404 })
    }

    return NextResponse.json(plan)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// PATCH /api/plans/[id] - Update plan (status, progress, currentTaskId)
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()
    const { status, progress, currentTaskId, description, goal, planType } = body

    const existing = await prisma.executionPlan.findUnique({ where: { id } })
    if (!existing) {
      return NextResponse.json({ error: 'Plan not found' }, { status: 404 })
    }

    const data: Record<string, unknown> = {}
    if (status !== undefined) data.status = status
    if (progress !== undefined) data.progress = progress
    if (currentTaskId !== undefined) data.currentTaskId = currentTaskId
    if (description !== undefined) data.description = description
    if (goal !== undefined) data.goal = goal
    if (planType !== undefined) data.planType = planType

    const plan = await prisma.executionPlan.update({
      where: { id },
      data,
    })

    return NextResponse.json(plan)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/plans/[id] - Delete plan
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params

    const existing = await prisma.executionPlan.findUnique({ where: { id } })
    if (!existing) {
      return NextResponse.json({ error: 'Plan not found' }, { status: 404 })
    }

    await prisma.executionPlan.delete({ where: { id } })

    return NextResponse.json({ success: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
