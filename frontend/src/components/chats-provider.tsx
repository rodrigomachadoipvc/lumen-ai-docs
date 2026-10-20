"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, type ChatSummary } from "@/lib/api";

interface ChatsContextValue {
  chats: ChatSummary[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const ChatsContext = createContext<ChatsContextValue | null>(null);

/** The chat list, shared by the sidebar and the chat pages so both stay in sync. */
export function ChatsProvider({ children }: { children: React.ReactNode }) {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setChats(await api.listChats());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load chats.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listChats()
      .then((loaded) => {
        if (cancelled) return;
        setChats(loaded);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load chats.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({ chats, loading, error, refresh }),
    [chats, loading, error, refresh],
  );
  return <ChatsContext.Provider value={value}>{children}</ChatsContext.Provider>;
}

export function useChats(): ChatsContextValue {
  const value = useContext(ChatsContext);
  if (!value) throw new Error("useChats must be used inside <ChatsProvider>");
  return value;
}
