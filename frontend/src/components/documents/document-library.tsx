"use client";

import { ExternalLinkIcon, RotateCwIcon, Trash2Icon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/documents/status-badge";
import { isAccepted, UploadZone } from "@/components/documents/upload-zone";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type LumenDocument, uploadDocument } from "@/lib/api";
import { formatBytes, formatDate, LANGUAGE_LABELS } from "@/lib/format";

interface Upload {
  key: string;
  name: string;
  progress: number;
}

const POLL_MS = 2000;

export function DocumentLibrary() {
  const [documents, setDocuments] = useState<LumenDocument[] | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [toDelete, setToDelete] = useState<LumenDocument | null>(null);

  const load = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not load documents.");
      setDocuments((current) => current ?? []);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listDocuments()
      .then((loaded) => !cancelled && setDocuments(loaded))
      .catch((err: unknown) => {
        if (cancelled) return;
        toast.error(err instanceof Error ? err.message : "Could not load documents.");
        setDocuments([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll while something is still being processed.
  const working = documents?.some((d) => d.status === "pending" || d.status === "processing");
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [working, load]);

  async function upload(files: File[]) {
    for (const file of files) {
      if (!isAccepted(file)) {
        toast.error(`${file.name}: only PDF, Markdown and text files are supported.`);
        continue;
      }
      const key = `${file.name}-${Date.now()}`;
      setUploads((current) => [...current, { key, name: file.name, progress: 0 }]);
      try {
        await uploadDocument(file, (progress) =>
          setUploads((current) => current.map((u) => (u.key === key ? { ...u, progress } : u))),
        );
        toast.success(`${file.name} uploaded. Processing…`);
      } catch (err) {
        toast.error(`${file.name}: ${err instanceof Error ? err.message : "upload failed"}`);
      } finally {
        setUploads((current) => current.filter((u) => u.key !== key));
        void load();
      }
    }
  }

  async function remove(document: LumenDocument) {
    setToDelete(null);
    try {
      await api.deleteDocument(document.id);
      toast.success(`${document.filename} deleted.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete the document.");
    }
    void load();
  }

  async function reprocess(document: LumenDocument) {
    try {
      await api.reprocessDocument(document.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not reprocess the document.");
    }
    void load();
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-sm text-muted-foreground">
            Files are processed on your computer: split into passages, embedded with Ollama and
            stored in PostgreSQL.
          </p>
        </div>

        <UploadZone onFiles={(files) => void upload(files)} />

        {uploads.length > 0 && (
          <ul className="space-y-2" aria-label="Uploads in progress">
            {uploads.map((u) => (
              <li key={u.key} className="text-sm">
                <div className="flex justify-between">
                  <span className="truncate">{u.name}</span>
                  <span className="text-muted-foreground">{Math.round(u.progress * 100)}%</span>
                </div>
                <progress
                  value={u.progress}
                  max={1}
                  aria-label={`Uploading ${u.name}`}
                  className="h-1.5 w-full overflow-hidden rounded-full accent-primary"
                />
              </li>
            ))}
          </ul>
        )}

        {documents === null ? (
          <div className="space-y-2" aria-label="Loading documents">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : documents.length === 0 ? (
          <p className="rounded-xl border p-6 text-center text-sm text-muted-foreground">
            No documents yet. Upload one above, or load the demo corpus with{" "}
            <code className="rounded bg-muted px-1">uv run python -m lumen.seed</code>.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden sm:table-cell">Details</TableHead>
                  <TableHead className="hidden xl:table-cell">Added</TableHead>
                  <TableHead className="text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((document) => (
                  <TableRow key={document.id}>
                    <TableCell className="max-w-56">
                      <a
                        href={api.documentFileUrl(document.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex max-w-full items-center gap-1 font-medium hover:underline"
                      >
                        <span className="truncate">{document.filename}</span>
                        <ExternalLinkIcon className="size-3 shrink-0" aria-hidden />
                      </a>
                      {document.error && (
                        <p className="text-xs whitespace-normal text-destructive">
                          {document.error}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={document.status} />
                    </TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground sm:table-cell">
                      {[
                        document.doc_type.toUpperCase(),
                        formatBytes(document.size_bytes),
                        document.page_count ? `${document.page_count} pages` : null,
                        document.status === "ready" ? `${document.chunk_count} passages` : null,
                        document.language ? LANGUAGE_LABELS[document.language] : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">
                      {formatDate(document.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      {document.status === "failed" && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => void reprocess(document)}
                          aria-label={`Process ${document.filename} again`}
                        >
                          <RotateCwIcon aria-hidden />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setToDelete(document)}
                        aria-label={`Delete ${document.filename}`}
                      >
                        <Trash2Icon aria-hidden />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <AlertDialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {toDelete?.filename}?</AlertDialogTitle>
            <AlertDialogDescription>
              The file and all its passages are removed. Old answers keep their text but their
              citations will no longer open.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => toDelete && void remove(toDelete)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
