"use client";

import { ExternalLinkIcon } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { api, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

interface SourcePanelProps {
  source: Source | null;
  onClose: () => void;
}

/** The exact passage behind a citation, with a link to the original file at that page. */
export function SourcePanel({ source, onClose }: SourcePanelProps) {
  return (
    <Sheet open={source !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-lg">
        {source && (
          <>
            <SheetHeader className="border-b">
              <SheetTitle className="flex items-center gap-2">
                <span className="inline-flex size-6 items-center justify-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
                  {source.number}
                </span>
                <span className="truncate">{source.filename}</span>
              </SheetTitle>
              <SheetDescription>
                {[source.page ? `Page ${source.page}` : null, source.heading_path.join(" › ")]
                  .filter(Boolean)
                  .join(" · ") || "Passage"}
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 overflow-y-auto p-4">
              <blockquote className="border-l-2 border-primary/40 pl-4 text-sm leading-7 whitespace-pre-wrap">
                {source.text}
              </blockquote>
              {source.similarity !== null && (
                <p className="mt-4 text-xs text-muted-foreground">
                  Semantic similarity to the question: {source.similarity.toFixed(2)}
                </p>
              )}
            </div>
            <div className="border-t p-4">
              <a
                href={api.documentFileUrl(source.document_id, source.page)}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(buttonVariants({ variant: "outline" }), "w-full")}
              >
                <ExternalLinkIcon aria-hidden />
                Open original{source.page ? ` at page ${source.page}` : ""}
              </a>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
