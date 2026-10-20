// Server-Sent Events over a POST response. EventSource only supports GET, so we read the
// fetch body ourselves and split it into events.

import { API_URL, type AgentStep, type AnswerMode, type Source, toApiError } from "@/lib/api";

export type StreamEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "delta"; text: string }
  | { type: "reset" }
  | { type: "step"; step: AgentStep }
  | {
      type: "done";
      answer: string;
      citations: Source[];
      grounded: boolean;
      model: string | null;
    }
  | { type: "error"; message: string }
  | { type: "saved"; user_message_id: string; assistant_message_id: string };

export interface RawEvent {
  event: string;
  data: string;
}

/** Parse complete events out of `buffer`; returns them plus the unfinished remainder. */
export function parseEvents(buffer: string): { events: RawEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: RawEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue; // comment / keep-alive
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
      if (field === "event") event = value;
      if (field === "data") data.push(value);
    }
    if (data.length) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

export function toStreamEvent(raw: RawEvent): StreamEvent | null {
  const data = JSON.parse(raw.data) as Record<string, unknown>;
  switch (raw.event) {
    case "sources":
      return { type: "sources", sources: data.sources as Source[] };
    case "delta":
      return { type: "delta", text: data.text as string };
    case "reset":
      return { type: "reset" };
    case "step":
      return { type: "step", step: data as unknown as AgentStep };
    case "done":
      return { type: "done", ...(data as Omit<Extract<StreamEvent, { type: "done" }>, "type">) };
    case "error":
      return { type: "error", message: data.message as string };
    case "saved":
      return {
        type: "saved",
        user_message_id: data.user_message_id as string,
        assistant_message_id: data.assistant_message_id as string,
      };
    default:
      return null;
  }
}

export async function* streamMessage(
  chatId: string,
  content: string,
  mode: AnswerMode,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_URL}/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content, mode }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw await toApiError(response);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseEvents(buffer + value);
    buffer = parsed.rest;
    for (const raw of parsed.events) {
      const event = toStreamEvent(raw);
      if (event) yield event;
    }
  }
}
