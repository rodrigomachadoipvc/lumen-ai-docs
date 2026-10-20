// Pure update rules for an assistant message while its answer streams in.

import type { ViewMessage } from "@/components/chat/message-bubble";
import type { ChatMessage } from "@/lib/api";
import type { StreamEvent } from "@/lib/sse";

export function emptyAssistant(id: string, agent: boolean): ViewMessage {
  return {
    id,
    role: "assistant",
    content: "",
    sources: [],
    citations: [],
    steps: [],
    grounded: null,
    model: null,
    error: null,
    streaming: true,
    agent,
  };
}

export function applyStreamEvent(message: ViewMessage, event: StreamEvent): ViewMessage {
  switch (event.type) {
    case "sources":
      return { ...message, sources: event.sources };
    case "delta":
      return { ...message, content: message.content + event.text };
    case "reset":
      return { ...message, content: "" };
    case "step":
      return { ...message, steps: [...message.steps, event.step] };
    case "done":
      return {
        ...message,
        content: event.answer,
        citations: event.citations,
        grounded: event.grounded,
        model: event.model,
      };
    case "error":
      return { ...message, error: event.message, streaming: false };
    case "saved":
      return { ...message, id: event.assistant_message_id, streaming: false };
  }
}

export function toViewMessage(message: ChatMessage): ViewMessage {
  return { ...message, streaming: false, agent: message.steps.length > 0 };
}
