import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AgentSteps } from "@/components/chat/agent-steps";
import { AnswerText } from "@/components/chat/answer-text";
import { Composer } from "@/components/chat/composer";
import { MessageBubble, type ViewMessage } from "@/components/chat/message-bubble";
import type { Source } from "@/lib/api";

const source: Source = {
  number: 1,
  chunk_id: "c1",
  document_id: "d1",
  filename: "regulamento.pdf",
  page: 3,
  heading_path: ["Artigo 7.º"],
  text: "O número máximo de dias de teletrabalho é de 3 dias por semana.",
  similarity: 0.84,
};

function assistant(overrides: Partial<ViewMessage> = {}): ViewMessage {
  return {
    id: "a1",
    role: "assistant",
    content: "São 3 dias por semana [1].",
    sources: [source],
    citations: [source],
    steps: [],
    grounded: true,
    model: "qwen3.5:4b",
    error: null,
    ...overrides,
  };
}

describe("AnswerText", () => {
  it("renders citations as buttons that open the source", async () => {
    const onCite = vi.fn();
    render(<AnswerText text="Três dias [1]." sources={[source]} onCite={onCite} />);

    await userEvent.click(screen.getByRole("button", { name: "Source 1: regulamento.pdf, p. 3" }));

    expect(onCite).toHaveBeenCalledWith(source);
  });

  it("never renders raw HTML from the model", () => {
    const { container } = render(
      <AnswerText text={'<img src=x onerror="alert(1)"> **bold**'} sources={[]} onCite={vi.fn()} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
  });
});

describe("MessageBubble", () => {
  it("shows cited sources and the model", () => {
    render(<MessageBubble message={assistant()} onCite={vi.fn()} />);

    expect(screen.getByText("regulamento.pdf, p. 3")).toBeInTheDocument();
    expect(screen.getByText("qwen3.5:4b")).toBeInTheDocument();
    expect(screen.queryByText("Not found in your documents")).not.toBeInTheDocument();
  });

  it("warns when the answer is not grounded", () => {
    render(
      <MessageBubble
        message={assistant({ content: "Não encontrei.", citations: [], grounded: false })}
        onCite={vi.fn()}
      />,
    );

    expect(screen.getByText("Not found in your documents")).toBeInTheDocument();
  });

  it("shows errors as alerts", () => {
    render(<MessageBubble message={assistant({ error: "Ollama is down" })} onCite={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Ollama is down");
  });

  it("shows progress while waiting", () => {
    render(
      <MessageBubble
        message={assistant({ content: "", sources: [], streaming: true })}
        onCite={vi.fn()}
      />,
    );

    expect(screen.getByText("Searching your documents…")).toBeInTheDocument();
  });
});

describe("Composer", () => {
  it("sends with Enter in the selected mode and clears the box", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const box = screen.getByLabelText("Ask a question about your documents");

    await userEvent.click(screen.getByRole("radio", { name: "Agent" }));
    await userEvent.type(box, "Quantos dias?{Enter}");

    expect(onSend).toHaveBeenCalledWith("Quantos dias?", "agent");
    expect(box).toHaveValue("");
  });

  it("keeps Shift+Enter as a new line and ignores empty input", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const box = screen.getByLabelText("Ask a question about your documents");

    await userEvent.type(box, "linha 1{Shift>}{Enter}{/Shift}linha 2");
    expect(box).toHaveValue("linha 1\nlinha 2");
    await userEvent.clear(box);
    await userEvent.type(box, "   {Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("offers a stop button while busy", async () => {
    const onStop = vi.fn();
    render(<Composer onSend={vi.fn()} onStop={onStop} busy />);

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    expect(onStop).toHaveBeenCalled();
  });
});

describe("AgentSteps", () => {
  it("lists tool calls with errors", async () => {
    render(
      <AgentSteps
        steps={[
          {
            index: 1,
            tool: "search_documents",
            arguments: { query: "férias" },
            summary: '"férias": 5 passages',
            sources: [1, 2],
            error: null,
            duration_ms: 1200,
          },
          {
            index: 2,
            tool: "get_document_section",
            arguments: { document: "x.pdf", page: 2 },
            summary: null,
            sources: [],
            error: "No document matches 'x.pdf'.",
            duration_ms: 5,
          },
        ]}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Agent used 2 tools/ }));

    expect(screen.getByText(/sources 1, 2/)).toBeInTheDocument();
    expect(screen.getByText("No document matches 'x.pdf'.")).toBeInTheDocument();
  });
});
