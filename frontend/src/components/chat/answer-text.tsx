"use client";

import ReactMarkdown, { type Components } from "react-markdown";

import type { Source } from "@/lib/api";
import { citationNumber, describeSource, linkCitations } from "@/lib/citations";

interface AnswerTextProps {
  text: string;
  sources: Source[];
  onCite: (source: Source) => void;
}

/** Renders the answer as Markdown (raw HTML is never rendered) with [n] as source buttons. */
export function AnswerText({ text, sources, onCite }: AnswerTextProps) {
  const byNumber = new Map(sources.map((s) => [s.number, s]));

  const components: Components = {
    a({ href, children }) {
      const number = citationNumber(href);
      const source = number ? byNumber.get(number) : undefined;
      if (source) {
        return (
          <button
            type="button"
            onClick={() => onCite(source)}
            aria-label={`Source ${source.number}: ${describeSource(source)}`}
            title={describeSource(source)}
            className="mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded-md bg-primary/10 px-1 align-middle text-[0.7rem] font-semibold text-primary hover:bg-primary/20 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {source.number}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
          {children}
        </a>
      );
    },
  };

  return (
    <div className="prose-answer space-y-2 leading-7 break-words [&_li]:ml-5 [&_ol]:list-decimal [&_strong]:font-semibold [&_ul]:list-disc">
      <ReactMarkdown components={components}>{linkCitations(text, sources.length)}</ReactMarkdown>
    </div>
  );
}
