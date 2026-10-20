"use client";

import { useParams } from "next/navigation";

import { ChatView } from "@/components/chat/chat-view";

export function ChatRoute() {
  const { id } = useParams<{ id: string }>();
  // A new key resets the view when switching chats.
  return <ChatView key={id} chatId={id} />;
}
