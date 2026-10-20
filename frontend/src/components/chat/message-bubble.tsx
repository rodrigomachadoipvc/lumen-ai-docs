"use client";

import { CircleAlertIcon, FileSearchIcon, TriangleAlertIcon } from "lucide-react";

import { AgentSteps } from "@/components/chat/agent-steps";
import { AnswerText } from "@/components/chat/answer-text";
import { Badge } from "@/components/ui/badge";
import type { AgentStep, Source } from "@/lib/api";
import { describeSource } from "@/lib/citations";

export interface ViewMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  citations: Source[];
  steps: AgentStep[];
  grounded: boolean | null;
  model: string | null;
  error: string | null;
  streaming?: boolean;
  agent?: boolean;
}

interface MessageBubbleProps {
  message: ViewMessage;
  onCite: (source: Source) => void;
}

export function MessageBubble({ message, onCite }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 whitespace-pre-wrap text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  const showSteps = message.steps.length > 0 || (message.streaming && message.agent);
  const waiting = message.streaming && !message.content && !showSteps;

  return (
    <article className="space-y-3" aria-busy={message.streaming}>
      {showSteps && <AgentSteps steps={message.steps} running={message.streaming} />}

      {waiting ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileSearchIcon className="size-4 animate-pulse" aria-hidden />
          {message.sources.length ? "Reading the passages…" : "Searching your documents…"}
        </p>
      ) : (
        message.content && (
          <AnswerText text={message.content} sources={message.sources} onCite={onCite} />
        )
      )}

      {message.error && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          {message.error}
        </p>
      )}

      {!message.streaming && !message.error && (
        <div className="flex flex-wrap items-center gap-2">
          {message.grounded === false && (
            <Badge variant="outline" className="gap-1 text-amber-700 dark:text-amber-400">
              <TriangleAlertIcon className="size-3" aria-hidden />
              Not found in your documents
            </Badge>
          )}
          {message.citations.map((source) => (
            <button
              key={source.number}
              type="button"
              onClick={() => onCite(source)}
              className="inline-flex max-w-64 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <span className="font-semibold text-primary">{source.number}</span>
              <span className="truncate">{describeSource(source)}</span>
            </button>
          ))}
          {message.model && (
            <span className="ml-auto text-xs text-muted-foreground">{message.model}</span>
          )}
        </div>
      )}
    </article>
  );
}
