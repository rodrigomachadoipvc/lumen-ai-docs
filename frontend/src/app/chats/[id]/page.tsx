import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { ChatRoute } from "./chat-route";

export default function ChatPage() {
  // The chat id is only known at request time, so it streams in behind this fallback.
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
          <Skeleton className="ml-auto h-10 w-2/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      }
    >
      <ChatRoute />
    </Suspense>
  );
}
