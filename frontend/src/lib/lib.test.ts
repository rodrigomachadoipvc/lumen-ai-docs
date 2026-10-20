import { describe, expect, it } from "vitest";

import type { Source } from "@/lib/api";
import { citationNumber, describeSource, linkCitations } from "@/lib/citations";
import { parseEvents, toStreamEvent } from "@/lib/sse";
import { applyStreamEvent, emptyAssistant } from "@/lib/stream-state";

const source: Source = {
  number: 1,
  chunk_id: "c1",
  document_id: "d1",
  filename: "reg.pdf",
  page: 3,
  heading_path: ["Capítulo II"],
  text: "Três dias.",
  similarity: 0.8,
};

describe("citations", () => {
  it("turns markers into links and leaves unknown numbers alone", () => {
    expect(linkCitations("Three days [1][2, 3]. Bad [9].", 3)).toBe(
      "Three days [1](#cite-1)[2](#cite-2)[3](#cite-3). Bad [9].",
    );
  });

  it("does not touch existing Markdown links", () => {
    expect(linkCitations("[1](https://example.com)", 3)).toBe("[1](https://example.com)");
  });

  it("reads citation numbers from hrefs", () => {
    expect(citationNumber("#cite-4")).toBe(4);
    expect(citationNumber("https://example.com")).toBeNull();
  });

  it("describes a source", () => {
    expect(describeSource(source)).toBe("reg.pdf, p. 3");
    expect(describeSource({ filename: "a.md", page: null })).toBe("a.md");
  });
});

describe("SSE parsing", () => {
  it("splits complete events and keeps the remainder", () => {
    const { events, rest } = parseEvents(
      'event: delta\ndata: {"text":"Hel"}\n\n: ping\n\nevent: delta\r\ndata: {"text":"lo"}\r\n\r\nevent: do',
    );

    expect(events).toEqual([
      { event: "delta", data: '{"text":"Hel"}' },
      { event: "delta", data: '{"text":"lo"}' },
    ]);
    expect(rest).toBe("event: do");
  });

  it("maps raw events to typed events", () => {
    expect(toStreamEvent({ event: "delta", data: '{"text":"a"}' })).toEqual({
      type: "delta",
      text: "a",
    });
    expect(toStreamEvent({ event: "reset", data: "{}" })).toEqual({ type: "reset" });
    expect(toStreamEvent({ event: "unknown", data: "{}" })).toBeNull();
  });
});

describe("stream state", () => {
  it("builds the answer from events", () => {
    let message = emptyAssistant("m1", true);
    message = applyStreamEvent(message, { type: "delta", text: "Let me look" });
    message = applyStreamEvent(message, { type: "reset" });
    message = applyStreamEvent(message, {
      type: "step",
      step: {
        index: 1,
        tool: "search_documents",
        arguments: { query: "x" },
        summary: "5 passages",
        sources: [1],
        error: null,
        duration_ms: 120,
      },
    });
    message = applyStreamEvent(message, { type: "sources", sources: [source] });
    message = applyStreamEvent(message, { type: "delta", text: "Três [1" });
    message = applyStreamEvent(message, {
      type: "done",
      answer: "Três dias [1].",
      citations: [source],
      grounded: true,
      model: "qwen3.5:4b",
    });

    expect(message.content).toBe("Três dias [1].");
    expect(message.steps).toHaveLength(1);
    expect(message.citations).toEqual([source]);
    expect(message.streaming).toBe(true); // until "saved"

    message = applyStreamEvent(message, {
      type: "saved",
      user_message_id: "u",
      assistant_message_id: "a",
    });
    expect(message.streaming).toBe(false);
  });

  it("records errors", () => {
    const message = applyStreamEvent(emptyAssistant("m", false), {
      type: "error",
      message: "Ollama is down",
    });

    expect(message).toMatchObject({ error: "Ollama is down", streaming: false });
  });
});
