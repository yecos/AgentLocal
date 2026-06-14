import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: ['query'],
  })

// Also export as default for compatibility with routes that use `import prisma from '@/lib/db'`
export default db

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = db
