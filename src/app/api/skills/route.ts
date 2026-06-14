import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/skills - List skills (with use counts, filterable by category)
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const category = searchParams.get('category')
    const enabled = searchParams.get('enabled')

    const where: Record<string, unknown> = {}
    if (category) where.category = category
    if (enabled !== null && enabled !== undefined) {
      where.enabled = enabled === 'true'
    }

    const skills = await prisma.skill.findMany({
      where,
      orderBy: { useCount: 'desc' },
    })

    return NextResponse.json({ skills })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/skills - Register a new skill
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { name, description, category, isTool, cliCommand, scriptPath, enabled, isLocal, config } = body

    if (!name || typeof name !== 'string') {
      return NextResponse.json(
        { error: 'name is required and must be a string' },
        { status: 400 }
      )
    }

    const skill = await prisma.skill.create({
      data: {
        name,
        description: description || null,
        category: category || 'general',
        isTool: isTool ?? false,
        cliCommand: cliCommand || null,
        scriptPath: scriptPath || null,
        enabled: enabled ?? true,
        isLocal: isLocal ?? true,
        config: config || null,
      },
    })

    return NextResponse.json(skill, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    if (message.includes('Unique constraint')) {
      return NextResponse.json({ error: 'Skill with this name already exists' }, { status: 409 })
    }
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// PATCH /api/skills - Update skill (enabled, use count)
export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json()
    const { id, name, enabled, useCount, description, category, isTool, cliCommand, scriptPath, config } = body

    if (!id && !name) {
      return NextResponse.json(
        { error: 'id or name is required' },
        { status: 400 }
      )
    }

    const where = id ? { id } : { name }
    const existing = await prisma.skill.findUnique({ where })
    if (!existing) {
      return NextResponse.json({ error: 'Skill not found' }, { status: 404 })
    }

    const data: Record<string, unknown> = {}
    if (enabled !== undefined) data.enabled = enabled
    if (useCount !== undefined) data.useCount = useCount
    if (description !== undefined) data.description = description
    if (category !== undefined) data.category = category
    if (isTool !== undefined) data.isTool = isTool
    if (cliCommand !== undefined) data.cliCommand = cliCommand
    if (scriptPath !== undefined) data.scriptPath = scriptPath
    if (config !== undefined) data.config = config
    if (useCount !== undefined || enabled !== undefined) data.lastUsedAt = new Date()

    const skill = await prisma.skill.update({
      where: { id: existing.id },
      data,
    })

    return NextResponse.json(skill)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
