import type { Page, Route } from "@playwright/test";

export const API = "http://localhost:8000";

export const SOURCE = {
  number: 1,
  chunk_id: "chunk-1",
  document_id: "doc-pdf",
  filename: "regulamento-teletrabalho.pdf",
  page: 3,
  heading_path: ["Capítulo II", "Artigo 7.º - Limite de dias em teletrabalho"],
  text: "O número máximo de dias de teletrabalho é de 3 dias por semana.",
  similarity: 0.84,
};

const now = "2026-10-20T20:00:00Z";

export function documentFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "doc-pdf",
    filename: "regulamento-teletrabalho.pdf",
    doc_type: "pdf",
    size_bytes: 10_600,
    status: "ready",
    error: null,
    language: "portuguese",
    page_count: 5,
    chunk_count: 17,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

export function sse(events: [string, unknown][]): string {
  return events
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");
}

interface MockOptions {
  documents?: Record<string, unknown>[];
  stream?: string;
}

/** Route every API call the UI makes to in-memory fixtures. */
export async function mockApi(page: Page, options: MockOptions = {}) {
  const chats: { id: string; title: string; created_at: string; updated_at: string }[] = [];
  let documents = options.documents ?? [documentFixture()];
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: body === undefined ? "" : JSON.stringify(body),
      headers: { "access-control-allow-origin": "*" },
    });

  await page.route(`${API}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const path = url.pathname;

    if (method === "OPTIONS") {
      return route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "*",
          "access-control-allow-headers": "*",
        },
      });
    }
    if (path === "/chats" && method === "GET") return json(route, chats);
    if (path === "/chats" && method === "POST") {
      const chat = {
        id: `chat-${chats.length + 1}`,
        title: "New chat",
        created_at: now,
        updated_at: now,
      };
      chats.unshift(chat);
      return json(route, chat, 201);
    }
    const chatMatch = path.match(/^\/chats\/([^/]+)$/);
    if (chatMatch && method === "GET") {
      const chat = chats.find((c) => c.id === chatMatch[1]);
      return chat
        ? json(route, { ...chat, messages: [] })
        : json(route, { error: { code: "not_found", message: "Chat not found." } }, 404);
    }
    if (/^\/chats\/[^/]+\/messages$/.test(path) && method === "POST") {
      const { content } = request.postDataJSON() as { content: string };
      if (chats[0]) chats[0].title = content;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "access-control-allow-origin": "*" },
        body:
          options.stream ??
          sse([
            ["sources", { sources: [SOURCE] }],
            ["delta", { text: "São 3 dias " }],
            ["delta", { text: "por semana [1]." }],
            [
              "done",
              {
                answer: "São 3 dias por semana [1].",
                citations: [SOURCE],
                grounded: true,
                model: "qwen3.5:4b",
              },
            ],
            ["saved", { user_message_id: "u1", assistant_message_id: "a1" }],
          ]),
      });
    }
    if (path === "/documents" && method === "GET") return json(route, documents);
    if (path === "/documents" && method === "POST") {
      const created = documentFixture({
        id: "doc-new",
        filename: "notas.md",
        doc_type: "markdown",
        status: "pending",
        chunk_count: 0,
        page_count: null,
        language: null,
      });
      documents = [created, ...documents];
      return json(route, created, 202);
    }
    const docMatch = path.match(/^\/documents\/([^/]+)$/);
    if (docMatch && method === "DELETE") {
      documents = documents.filter((d) => d.id !== docMatch[1]);
      return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*" } });
    }
    return json(
      route,
      { error: { code: "not_found", message: `No mock for ${method} ${path}` } },
      404,
    );
  });
}
