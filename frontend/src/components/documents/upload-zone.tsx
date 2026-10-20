"use client";

import { UploadIcon } from "lucide-react";
import { type DragEvent, useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export const ACCEPTED = ".pdf,.md,.markdown,.txt";
const ACCEPTED_EXTENSIONS = ACCEPTED.split(",");

export function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function UploadZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    onFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
        dragging ? "border-primary bg-primary/5" : "border-border",
      )}
    >
      <UploadIcon className="size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm">
        Drag files here, or{" "}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="font-medium text-primary underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
        >
          choose files
        </button>
      </p>
      <p id={hintId} className="text-xs text-muted-foreground">
        PDF, Markdown or plain text (UTF-8), up to 25 MB each
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED}
        aria-describedby={hintId}
        aria-label="Choose files to upload"
        className="sr-only"
        onChange={(event) => {
          onFiles(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
    </div>
  );
}
