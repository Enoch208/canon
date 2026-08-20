import { NextResponse } from "next/server"

import { ask } from "@/lib/api"

export async function POST(request: Request) {
  const body = (await request.json()) as { question?: string; mode?: string; top_k?: number }
  if (!body.question) {
    return NextResponse.json({ detail: "question is required" }, { status: 400 })
  }
  try {
    const response = await ask(body.question, body.mode ?? "current", body.top_k ?? 10)
    return NextResponse.json(response)
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : "ask failed"
    return NextResponse.json({ detail }, { status: 502 })
  }
}
