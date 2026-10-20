"use client";

import { FileTextIcon, MenuIcon, MessageSquareIcon, PlusIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState } from "react";

import { useChats } from "@/components/chats-provider";
import { ModeToggle } from "@/components/mode-toggle";
import { Button, buttonVariants } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { chats, loading, error } = useChats();

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <Link
        href="/"
        onClick={onNavigate}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-lg font-semibold tracking-tight"
      >
        <SparklesIcon className="size-5 text-primary" aria-hidden />
        Lumen
      </Link>

      <nav aria-label="Main" className="flex flex-col gap-1">
        <Link
          href="/"
          onClick={onNavigate}
          className={cn(buttonVariants({ variant: "default" }), "justify-start")}
        >
          <PlusIcon aria-hidden /> New chat
        </Link>
        <Link
          href="/documents"
          onClick={onNavigate}
          aria-current={pathname === "/documents" ? "page" : undefined}
          className={cn(
            buttonVariants({ variant: "ghost" }),
            "justify-start",
            pathname === "/documents" && "bg-muted",
          )}
        >
          <FileTextIcon aria-hidden /> Documents
        </Link>
      </nav>

      <Separator />

      <h2 className="px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Chats
      </h2>
      <ScrollArea className="-mx-1 min-h-0 flex-1 px-1">
        {loading ? (
          <div className="space-y-2 px-1" aria-label="Loading chats">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        ) : error ? (
          <p className="px-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : chats.length === 0 ? (
          <p className="px-2 text-sm text-muted-foreground">No chats yet.</p>
        ) : (
          <ul className="space-y-0.5">
            {chats.map((chat) => {
              const href = `/chats/${chat.id}`;
              const active = pathname === href;
              return (
                <li key={chat.id}>
                  <Link
                    href={href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                      active && "bg-muted font-medium",
                    )}
                  >
                    <MessageSquareIcon
                      className="size-3.5 shrink-0 text-muted-foreground"
                      aria-hidden
                    />
                    <span className="truncate">{chat.title}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>

      <div className="flex items-center justify-between border-t pt-3">
        <span className="px-2 text-xs text-muted-foreground">Runs locally</span>
        <ModeToggle />
      </div>
    </div>
  );
}

function SidebarSkeleton() {
  return (
    <div className="space-y-3 p-3" aria-hidden>
      <Skeleton className="h-8 w-24" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <aside className="hidden w-64 shrink-0 border-r bg-sidebar md:block" aria-label="Sidebar">
        {/* The sidebar reads the current URL, which is only known at request time. */}
        <Suspense fallback={<SidebarSkeleton />}>
          <Sidebar />
        </Suspense>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b px-3 py-2 md:hidden">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon" aria-label="Open menu" />}>
              <MenuIcon aria-hidden />
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-0">
              <SheetTitle className="sr-only">Menu</SheetTitle>
              <Suspense fallback={<SidebarSkeleton />}>
                <Sidebar onNavigate={() => setOpen(false)} />
              </Suspense>
            </SheetContent>
          </Sheet>
          <span className="font-semibold">Lumen</span>
        </header>
        <main id="main" className="flex min-h-0 flex-1 flex-col">
          {children}
        </main>
      </div>
    </div>
  );
}
