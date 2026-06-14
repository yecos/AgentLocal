import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// PATCH /api/plans/[id]/tasks/[taskId] - Update a single task
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; taskId: string }> }
) {
  try {
    const { id, taskId } = await params
    const body = await request.json()
    const { title, description, status, priority, order, result, error } = body

    const existing = await prisma.task.findFirst({ where: { id: taskId, planId: id } })
    if (!existing) {
      return NextResponse.json({ error: 'Task not found' }, { status: 404 })
    }

    const data: Record<string, unknown> = {}
    if (title !== undefined) data.title = title
    if (description !== undefined) data.description = description
    if (status !== undefined) data.status = status
    if (priority !== undefined) data.priority = priority
    if (order !== undefined) data.order = order
    if (result !== undefined) data.result = result
    if (error !== undefined) data.error = error

    const task = await prisma.task.update({
      where: { id: taskId },
      data,
    })

    return NextResponse.json(task)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// DELETE /api/plans/[id]/tasks/[taskId] - Delete a single task
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string; taskId: string }> }
) {
  try {
    const { id, taskId } = await params

    const existing = await prisma.task.findFirst({ where: { id: taskId, planId: id } })
    if (!existing) {
      return NextResponse.json({ error: 'Task not found' }, { status: 404 })
    }

    await prisma.task.delete({ where: { id: taskId } })

    return NextResponse.json({ success: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
