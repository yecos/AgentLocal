import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// PATCH /api/plans/[id]/tasks/[taskId] - Update task (status, result, error)
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; taskId: string }> }
) {
  try {
    const { id, taskId } = await params
    const body = await request.json()
    const { status, result, error, priority, dependencies, attempts, startedAt, completedAt } = body

    const task = await prisma.task.findFirst({ where: { id: taskId, planId: id } })
    if (!task) {
      return NextResponse.json({ error: 'Task not found' }, { status: 404 })
    }

    const data: Record<string, unknown> = {}
    if (status !== undefined) data.status = status
    if (result !== undefined) data.result = result
    if (error !== undefined) data.error = error
    if (priority !== undefined) data.priority = priority
    if (dependencies !== undefined) data.dependencies = dependencies
    if (attempts !== undefined) data.attempts = attempts
    if (startedAt !== undefined) data.startedAt = startedAt
    if (completedAt !== undefined) data.completedAt = completedAt

    const updated = await prisma.task.update({
      where: { id: taskId },
      data,
    })

    return NextResponse.json(updated)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/plans/[id]/tasks/[taskId] - Delete task
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string; taskId: string }> }
) {
  try {
    const { id, taskId } = await params

    const task = await prisma.task.findFirst({ where: { id: taskId, planId: id } })
    if (!task) {
      return NextResponse.json({ error: 'Task not found' }, { status: 404 })
    }

    await prisma.task.delete({ where: { id: taskId } })

    return NextResponse.json({ success: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
