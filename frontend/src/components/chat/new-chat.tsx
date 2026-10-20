"use client";

import { SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { useChats } from "@/components/chats-provider";
import { PENDING_KEY } from "@/components/chat/chat-view";
import { Composer } from "@/components/chat/composer";
import { type AnswerMode, api } from "@/lib/api";

const EXAMPLES = [
  "Quantos dias por semana posso estar em teletrabalho?",
  "How many vacation days do I get?",
  "Durante quanto tempo são guardados os dados de faturação?",
  "Which planet rotates on its side?",
];

export function NewChat() {
  const router = useRouter();
  const { refresh } = useChats();
  const [busy, setBusy] = useState(false);

  async function start(content: string, mode: AnswerMode) {
    setBusy(true);
    try {
      const chat = await api.createChat();
      sessionStorage.setItem(PENDING_KEY(chat.id), JSON.stringify({ content, mode }));
      void refresh();
      router.push(`/chats/${chat.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start a chat.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10">
      <div className="w-full max-w-2xl space-y-8">
        <div className="space-y-3 text-center">
          <SparklesIcon className="mx-auto size-8 text-primary" aria-hidden />
          <h1 className="text-3xl font-semibold tracking-tight">Ask your documents</h1>
          <p className="text-muted-foreground">
            Every answer cites the exact passages and pages it comes from. Add files in{" "}
            <Link href="/documents" className="font-medium text-foreground underline">
              Documents
            </Link>
            .
          </p>
        </div>
        <Composer onSend={start} busy={busy} autoFocus />
        <div>
          <h2 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Try with the demo documents
          </h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void start(example, "answer")}
                  className="h-full w-full rounded-xl border p-3 text-left text-sm hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
