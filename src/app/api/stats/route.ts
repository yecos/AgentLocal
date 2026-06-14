import { NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/stats - Get dashboard statistics
export async function GET() {
  try {
    const [
      conversationCount,
      planCount,
      activePlanCount,
      taskCount,
      completedTaskCount,
      failedTaskCount,
      memoryCount,
      projectCount,
      skillCount,
      enabledSkillCount,
      noteCount,
      toolCallCount,
      recentToolCalls,
      successfulToolCalls,
      totalToolCallsForRate,
    ] = await Promise.all([
      prisma.conversation.count(),
      prisma.executionPlan.count(),
      prisma.executionPlan.count({ where: { status: 'active' } }),
      prisma.task.count(),
      prisma.task.count({ where: { status: 'completed' } }),
      prisma.task.count({ where: { status: 'failed' } }),
      prisma.memoryEntry.count(),
      prisma.project.count(),
      prisma.skill.count(),
      prisma.skill.count({ where: { enabled: true } }),
      prisma.note.count(),
      prisma.toolCallLog.count(),
      // Recent tool calls (last 24 hours)
      prisma.toolCallLog.count({
        where: {
          createdAt: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) },
        },
      }),
      // Successful tool calls for rate calculation
      prisma.toolCallLog.count({ where: { success: true } }),
      prisma.toolCallLog.count(),
    ])

    const successRate = totalToolCallsForRate > 0
      ? Math.round((successfulToolCalls / totalToolCallsForRate) * 100)
      : 0

    // Top tools by usage
    const topTools = await prisma.toolCallLog.groupBy({
      by: ['tool'],
      _count: { tool: true },
      orderBy: { _count: { tool: 'desc' } },
      take: 10,
    })

    // Tasks by status
    const tasksByStatus = await prisma.task.groupBy({
      by: ['status'],
      _count: { status: true },
    })

    // Memory by type
    const memoryByType = await prisma.memoryEntry.groupBy({
      by: ['type'],
      _count: { type: true },
    })

    return NextResponse.json({
      conversations: {
        total: conversationCount,
      },
      plans: {
        total: planCount,
        active: activePlanCount,
      },
      tasks: {
        total: taskCount,
        completed: completedTaskCount,
        failed: failedTaskCount,
        byStatus: Object.fromEntries(tasksByStatus.map(s => [s.status, s._count.status])),
      },
      memory: {
        total: memoryCount,
        byType: Object.fromEntries(memoryByType.map(m => [m.type, m._count.type])),
      },
      projects: {
        total: projectCount,
      },
      skills: {
        total: skillCount,
        enabled: enabledSkillCount,
      },
      notes: {
        total: noteCount,
      },
      toolCalls: {
        total: toolCallCount,
        last24h: recentToolCalls,
        successRate,
        topTools: topTools.map(t => ({ name: t.tool, count: t._count.tool })),
      },
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
