import type { Metadata } from "next";

import { DocumentLibrary } from "@/components/documents/document-library";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return <DocumentLibrary />;
}
