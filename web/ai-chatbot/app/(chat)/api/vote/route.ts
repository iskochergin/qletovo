import { NextResponse } from "next/server";

// Stubbed votes endpoint to avoid 404s in the UI.
export async function GET() {
  return NextResponse.json([]);
}
