"use client";

import { useState } from "react";
import { ChevronRightIcon, CircleAlertIcon, CircleCheckIcon, WrenchIcon } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { AgentStep } from "@/lib/api";

const TOOL_LABELS: Record<string, string> = {
  search_documents: "Searched",
  get_document_section: "Read section",
  compare_documents: "Compared documents",
  list_documents: "Listed documents",
};

function formatArguments(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join(" · ");
}

export function AgentSteps({ steps, running = false }: { steps: AgentStep[]; running?: boolean }) {
  // Open while the agent works (so progress is visible); afterwards the user decides.
  const [open, setOpen] = useState(running);
  if (!steps.length && !running) return null;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-lg border bg-muted/30 text-sm"
    >
      <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 text-left font-medium focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
        <ChevronRightIcon
          className="size-4 transition-transform group-data-panel-open:rotate-90"
          aria-hidden
        />
        <WrenchIcon className="size-4 text-muted-foreground" aria-hidden />
        {running && !steps.length
          ? "Agent is planning…"
          : `Agent used ${steps.length} tool${steps.length === 1 ? "" : "s"}`}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="relative ml-5 space-y-3 border-l px-4 pt-1 pb-3" aria-label="Agent steps">
          {steps.map((step) => (
            <li key={step.index} className="relative">
              <span className="absolute top-0.5 -left-[1.4rem] rounded-full bg-background">
                {step.error ? (
                  <CircleAlertIcon className="size-4 text-destructive" aria-label="Failed" />
                ) : (
                  <CircleCheckIcon className="size-4 text-primary" aria-label="Done" />
                )}
              </span>
              <p className="font-medium">
                {TOOL_LABELS[step.tool] ?? step.tool}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {(step.duration_ms / 1000).toFixed(1)} s
                </span>
              </p>
              {Object.keys(step.arguments).length > 0 && (
                <p className="text-xs break-words text-muted-foreground">
                  {formatArguments(step.arguments)}
                </p>
              )}
              <p className={step.error ? "text-xs text-destructive" : "text-xs"}>
                {step.error ?? step.summary}
                {step.sources.length > 0 && ` → sources ${step.sources.join(", ")}`}
              </p>
            </li>
          ))}
          {running && <li className="text-xs text-muted-foreground">Working…</li>}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
