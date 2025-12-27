import { NextResponse } from "next/server";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8765/ask";
// По умолчанию работаем в режиме заглушки; чтобы включить реальный бэкенд
// выстави QLETOVO_STUB=false (или поменяй переменную ниже).
const USE_STUB = (process.env.QLETOVO_STUB ?? "true").toLowerCase() !== "false";

type IncomingMessage = {
  role: string;
  parts?: Array<{ type: string; text?: string }>;
};

type IncomingBody = {
  id?: string;
  message?: IncomingMessage;
  messages?: IncomingMessage[];
};

function normalizeToMarkdown(text: string) {
  return text
    // "• item" в начале строки -> "- item"
    .replace(/^\s*•\s+/gm, "- ")
    // inline bullets -> перенос и маркер
    .replace(/\s*•\s+/g, "\n- ")
    // лишние пустые строки до двух подряд
    .replace(/\n{3,}/g, "\n\n");
}

function pickStubAnswer() {
  const examples = [
    [
      "Основные документы для поступления:",
      "1) Заявление от родителя/опекуна",
      "2) Паспорт или свидетельство о рождении",
      "3) Аттестат или текущая выписка оценок",
      "Источник: Памятка абитуриента",
      "https://qletovo.ru",
    ].join("\n"),
    [
      "Расписание учебного дня:",
      "• Утренние занятия: 08:30 – 12:10",
      "• Обед: 12:10 – 13:00",
      "• Вторая половина дня: 13:00 – 17:00",
      "Источник: График учебного процесса",
      "https://qletovo.ru",
    ].join("\n"),
    [
      "Система оценивания в «Летово»:",
      "- Формирующее оценивание (feedback)",
      "- Констатирующее оценивание (за темы/модули)",
      "- Итоговая отметка по 7-балльной шкале",
      "Источник: Положение об оценивании",
      "https://qletovo.ru",
    ].join("\n"),
    [
      "Правила поведения:",
      "• Соблюдать дресс-код",
      "• Не опаздывать на занятия",
      "• Бережно относиться к оборудованию",
      "Источник: Кодекс учащегося",
      "https://qletovo.ru",
    ].join("\n"),
  ];

  const idx = Math.floor(Math.random() * examples.length);
  return examples[idx];
}

function streamTextResponse(answer: string) {
  const messageId = crypto.randomUUID();
  const textId = crypto.randomUUID();

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      const send = (obj: unknown) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));

      // Data Stream Protocol expected by AI SDK UI
      send({ type: "start", messageId });
      send({ type: "text-start", id: textId });
      send({ type: "text-delta", id: textId, delta: answer });
      send({ type: "text-end", id: textId });
      send({ type: "finish" });

      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

export async function POST(request: Request) {
  let body: IncomingBody;
  try {
    body = (await request.json()) as IncomingBody;
  } catch {
    return NextResponse.json({ error: "bad_request" }, { status: 400 });
  }

  console.log("[qletovo] mode", USE_STUB ? "stub" : "backend");

  if (USE_STUB) {
    const stub = normalizeToMarkdown(pickStubAnswer());
    console.log("[qletovo] stub response", stub);
    return streamTextResponse(stub);
  }

  const backendUrl = process.env.QLETOVO_API_URL?.trim() || DEFAULT_BACKEND_URL;
  const question =
    body.message?.parts?.find((p) => p.type === "text")?.text ??
    "Задай свой вопрос";

  try {
    const backendResponse = await fetch(backendUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, temperature: 0 }),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      throw new Error(errorText || "Backend error");
    }

    const data = await backendResponse.json();
    console.log("[qletovo] incoming parsed", data);
    const answerRaw =
      typeof data === "object" && data?.answer
        ? data.answer
        : typeof data === "string"
          ? data
          : data?.text ?? "Нет ответа.";
    const sources = Array.isArray((data as any)?.sources)
      ? ((data as any)?.sources as Array<{ title?: string; url?: string }>)
      : [];
    const mainSource = sources.find((src) => src?.url);

    const answerNormalized = Array.isArray(answerRaw)
      ? answerRaw.map((item: any, idx: number) => `${idx + 1}. ${item}`).join("\n")
      : String(answerRaw);

    // Нормализуем bullets в markdown-список, сохраняем переносы
    const normalized = normalizeToMarkdown(answerNormalized);

    const responseText = mainSource?.url
      ? `${normalized}\n\nИсточник: ${mainSource.title ?? "Документ"}\n${mainSource.url}`
      : normalized;

    console.log("[qletovo] normalized response", {
      textPreview: responseText.slice(0, 120),
      hasSource: Boolean(mainSource?.url),
    });

    return streamTextResponse(responseText);
  } catch (error: any) {
    console.error("[qletovo] error", error);
    // Фолбэк на заглушку, если реальный бэкенд недоступен
    const stub = normalizeToMarkdown(pickStubAnswer());
    console.log("[qletovo] fallback to stub");
    return streamTextResponse(stub);
  }
}
