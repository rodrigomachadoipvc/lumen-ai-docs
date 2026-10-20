import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-24">
      <h1 className="text-4xl font-semibold tracking-tight">Lumen</h1>
      <p className="text-lg leading-8 text-muted-foreground">
        Ask questions about your documents. Every answer cites the exact passages and pages it comes
        from.
      </p>
      <div>
        <Button disabled>Upload a document (coming soon)</Button>
      </div>
    </main>
  );
}
