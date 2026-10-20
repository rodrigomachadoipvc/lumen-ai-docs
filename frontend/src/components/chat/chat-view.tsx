"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useChats } from "@/components/chats-provider";
import { Composer } from "@/components/chat/composer";
import { MessageBubble, type ViewMessage } from "@/components/chat/message-bubble";
import { SourcePanel } from "@/components/chat/source-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, type AnswerMode, api, type Source } from "@/lib/api";
import { streamMessage } from "@/lib/sse";
import { applyStreamEvent, emptyAssistant, toViewMessage } from "@/lib/stream-state";

export const PENDING_KEY = (chatId: string) => `lumen:pending:${chatId}`;

export function ChatView({ chatId }: { chatId: string }) {
  const router = useRouter();
  const { chats, refresh } = useChats();
  const [title, setTitle] = useState("");
  const [messages, setMessages] = useState<ViewMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const startedRef = useRef(false);

  const send = useCallback(
    async (content: string, mode: AnswerMode) => {
      const assistantId = `pending-${Date.now()}`;
      const userMessage: ViewMessage = {
        ...emptyAssistant(`user-${Date.now()}`, false),
        role: "user",
        content,
        streaming: false,
      };
      setMessages((current) => [
        ...current,
        userMessage,
        emptyAssistant(assistantId, mode === "agent"),
      ]);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      const update = (fn: (m: ViewMessage) => ViewMessage) =>
        setMessages((current) => current.map((m) => (m.id === assistantId ? fn(m) : m)));
      try {
        for await (const event of streamMessage(chatId, content, mode, controller.signal)) {
          if (event.type === "saved") {
            // Keep the temporary id until the end so updates keep finding the message.
            update((m) => ({ ...m, streaming: false }));
          } else {
            update((m) => applyStreamEvent(m, event));
          }
        }
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === "AbortError";
        update((m) => ({
          ...m,
          streaming: false,
          error: aborted
            ? "Stopped. The answer is still being saved in the background."
            : err instanceof Error
              ? err.message
              : "Something went wrong.",
        }));
      } finally {
        update((m) => ({ ...m, streaming: false }));
        setBusy(false);
        abortRef.current = null;
        void refresh(); // the title and order of chats may have changed
      }
    },
    [chatId, refresh],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .getChat(chatId)
      .then((chat) => {
        if (cancelled) return;
        setTitle(chat.title);
        setMessages(chat.messages.map(toViewMessage));
        setLoading(false);
        // A question typed on the home page is sent once the chat exists.
        const pending = sessionStorage.getItem(PENDING_KEY(chatId));
        if (pending && !startedRef.current) {
          startedRef.current = true;
          sessionStorage.removeItem(PENDING_KEY(chatId));
          const { content, mode } = JSON.parse(pending) as { content: string; mode: AnswerMode };
          void send(content, mode);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          toast.error("That chat no longer exists.");
          router.replace("/");
        } else {
          toast.error(err instanceof Error ? err.message : "Could not load the chat.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chatId, router, send]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b px-4 py-3">
        <h1 className="truncate font-semibold">
          {chats.find((chat) => chat.id === chatId)?.title ?? (title || "Chat")}
        </h1>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div
          className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6"
          aria-live="polite"
          aria-relevant="additions text"
        >
          {loading ? (
            <div className="space-y-4" aria-label="Loading messages">
              <Skeleton className="ml-auto h-10 w-2/3" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : (
            messages.map((message) => (
              <MessageBubble key={message.id} message={message} onCite={setOpenSource} />
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl px-4 pb-4">
        <Composer onSend={send} busy={busy} onStop={() => abortRef.current?.abort()} autoFocus />
      </div>

      <SourcePanel source={openSource} onClose={() => setOpenSource(null)} />
    </div>
  );
}
