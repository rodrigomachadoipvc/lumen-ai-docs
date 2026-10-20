"use client";

import { ArrowUpIcon, SquareIcon } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { AnswerMode } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ComposerProps {
  onSend: (content: string, mode: AnswerMode) => void;
  onStop?: () => void;
  busy?: boolean;
  autoFocus?: boolean;
}

const MODES: { value: AnswerMode; label: string; hint: string }[] = [
  { value: "answer", label: "Answer", hint: "One search, fast answer" },
  { value: "agent", label: "Agent", hint: "Several steps for complex questions" },
];

export function Composer({ onSend, onStop, busy = false, autoFocus = false }: ComposerProps) {
  const [content, setContent] = useState("");
  const [mode, setMode] = useState<AnswerMode>("answer");
  const inputId = useId();
  const hintId = useId();

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = content.trim();
    if (!text || busy) return;
    onSend(text, mode);
    setContent("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border bg-background p-2 shadow-sm focus-within:ring-3 focus-within:ring-ring/30"
    >
      <label htmlFor={inputId} className="sr-only">
        Ask a question about your documents
      </label>
      <Textarea
        id={inputId}
        value={content}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask a question about your documents…"
        aria-describedby={hintId}
        autoFocus={autoFocus}
        rows={2}
        maxLength={4000}
        className="max-h-48 min-h-12 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      <div className="flex items-center justify-between gap-2 px-1 pt-1">
        <div role="radiogroup" aria-label="Answer mode" className="flex rounded-lg bg-muted p-0.5">
          {MODES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={mode === option.value}
              title={option.hint}
              onClick={() => setMode(option.value)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                mode === option.value && "bg-background text-foreground shadow-sm",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p id={hintId} className="hidden text-xs text-muted-foreground sm:block">
          Enter to send · Shift+Enter for a new line
        </p>
        {busy ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop">
            <SquareIcon aria-hidden />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!content.trim()} aria-label="Send">
            <ArrowUpIcon aria-hidden />
          </Button>
        )}
      </div>
    </form>
  );
}
