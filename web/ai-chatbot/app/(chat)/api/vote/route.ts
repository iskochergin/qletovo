import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

const VOTES_PATH = path.join(process.cwd(), "data", "votes.json");

type VoteRecord = {
  chatId: string;
  messageId: string;
  isUpvoted: boolean;
  messageText?: string;
  userMessageText?: string;
  updatedAt: string;
};

async function readVotes(): Promise<VoteRecord[]> {
  try {
    const raw = await fs.readFile(VOTES_PATH, "utf8");
    return JSON.parse(raw) as VoteRecord[];
  } catch (error: any) {
    // If file doesn't exist, start fresh
    if (error.code === "ENOENT") {
      await fs.mkdir(path.dirname(VOTES_PATH), { recursive: true });
      await fs.writeFile(VOTES_PATH, "[]", "utf8");
      return [];
    }
    throw error;
  }
}

async function writeVotes(votes: VoteRecord[]) {
  await fs.mkdir(path.dirname(VOTES_PATH), { recursive: true });
  await fs.writeFile(VOTES_PATH, JSON.stringify(votes, null, 2), "utf8");
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const chatIdFilter = searchParams.get("chatId");

  const votes = await readVotes();
  const filtered = chatIdFilter
    ? votes.filter((v) => v.chatId === chatIdFilter)
    : votes;

  return NextResponse.json(filtered);
}

export async function PATCH(request: Request) {
  try {
    const body = (await request.json()) as {
      chatId?: string;
      messageId?: string;
      type?: "up" | "down";
      messageText?: string;
    };

    if (!body.chatId || !body.messageId || !body.type) {
      return NextResponse.json(
        { error: "missing_fields" },
        { status: 400 }
      );
    }

    const votes = await readVotes();
    const idx = votes.findIndex(
      (v) => v.chatId === body.chatId && v.messageId === body.messageId
    );

    const record: VoteRecord = {
      chatId: body.chatId,
      messageId: body.messageId,
      isUpvoted: body.type === "up",
      messageText: body.messageText ?? "",
      userMessageText: (body as any).userMessageText ?? "",
      updatedAt: new Date().toISOString(),
    };

    if (idx >= 0) {
      votes[idx] = record;
    } else {
      votes.push(record);
    }

    await writeVotes(votes);

    return NextResponse.json(record);
  } catch (error) {
    console.error("[vote] error", error);
    return NextResponse.json({ error: "server_error" }, { status: 500 });
  }
}
