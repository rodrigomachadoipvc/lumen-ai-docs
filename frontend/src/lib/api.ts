// Typed client for the Lumen API. Every error response has the shape
// {"error": {"code", "message", "details"}} and is thrown as an ApiError.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";
export type DocumentType = "pdf" | "markdown" | "text";
export type AnswerMode = "answer" | "agent";

export interface LumenDocument {
  id: string;
  filename: string;
  doc_type: DocumentType;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  language: string | null;
  page_count: number | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface Source {
  number: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number | null;
  heading_path: string[];
  text: string;
  similarity: number | null;
}

export interface AgentStep {
  index: number;
  tool: string;
  arguments: Record<string, unknown>;
  summary: string | null;
  sources: number[];
  error: string | null;
  duration_ms: number;
}

export interface ChatSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  citations: Source[];
  steps: AgentStep[];
  grounded: boolean | null;
  model: string | null;
  error: string | null;
  created_at: string;
}

export interface ChatDetail extends ChatSummary {
  messages: ChatMessage[];
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    return new ApiError(
      response.status,
      body.error?.code ?? "http_error",
      body.error?.message ?? response.statusText,
      body.error?.details ?? null,
    );
  } catch {
    return new ApiError(response.status, "http_error", response.statusText || "Request failed");
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the Lumen API at ${API_URL}.`);
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  listDocuments: () => request<LumenDocument[]>("/documents"),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  reprocessDocument: (id: string) =>
    request<LumenDocument>(`/documents/${id}/reprocess`, { method: "POST" }),
  documentFileUrl: (id: string, page?: number | null) =>
    `${API_URL}/documents/${id}/file${page ? `#page=${page}` : ""}`,

  listChats: () => request<ChatSummary[]>("/chats"),
  createChat: () => request<ChatSummary>("/chats", { method: "POST", body: "{}" }),
  getChat: (id: string) => request<ChatDetail>(`/chats/${id}`),
  renameChat: (id: string, title: string) =>
    request<ChatSummary>(`/chats/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteChat: (id: string) => request<void>(`/chats/${id}`, { method: "DELETE" }),
};

/** Upload with progress events (fetch cannot report upload progress). */
export function uploadDocument(
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<LumenDocument> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/documents`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      const response = new Response(xhr.responseText, { status: xhr.status });
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as LumenDocument);
      } else {
        void toApiError(response).then(reject);
      }
    };
    xhr.onerror = () =>
      reject(new ApiError(0, "network_error", `Cannot reach the Lumen API at ${API_URL}.`));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
