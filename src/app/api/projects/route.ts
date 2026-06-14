import { NextRequest, NextResponse } from 'next/server'
import prisma from '@/lib/db'

// GET /api/projects - List projects
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status') || 'active'
    const framework = searchParams.get('framework')

    const where: Record<string, unknown> = { status }
    if (framework) where.framework = framework

    const projects = await prisma.project.findMany({
      where,
      orderBy: { updatedAt: 'desc' },
    })

    return NextResponse.json({ projects })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

// POST /api/projects - Add a project
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { name, path, description, framework, language, gitRepo, userId } = body

    if (!name || typeof name !== 'string') {
      return NextResponse.json(
        { error: 'name is required and must be a string' },
        { status: 400 }
      )
    }

    if (!path || typeof path !== 'string') {
      return NextResponse.json(
        { error: 'path is required and must be a string' },
        { status: 400 }
      )
    }

    const project = await prisma.project.create({
      data: {
        name,
        path,
        description: description || null,
        framework: framework || null,
        language: language || null,
        gitRepo: gitRepo || null,
        userId: userId || null,
      },
    })

    return NextResponse.json(project, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
