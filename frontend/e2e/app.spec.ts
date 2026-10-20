import { expect, test } from "@playwright/test";

import { documentFixture, mockApi, SOURCE, sse } from "./mock-api";

test("ask a question and open the cited passage", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  const box = page.getByLabel("Ask a question about your documents");
  await box.fill("Quantos dias por semana posso estar em teletrabalho?");
  await box.press("Enter");

  await expect(page).toHaveURL(/\/chats\/chat-1$/);
  await expect(page.getByText("São 3 dias por semana")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Quantos dias por semana posso estar em teletrabalho?",
  );

  await page.getByRole("button", { name: "Source 1: regulamento-teletrabalho.pdf, p. 3" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel).toContainText(SOURCE.text);
  await expect(panel).toContainText("Page 3");
  await expect(panel.getByRole("link", { name: /Open original at page 3/ })).toHaveAttribute(
    "href",
    "http://localhost:8000/documents/doc-pdf/file#page=3",
  );
});

test("agent mode shows the tool steps", async ({ page }) => {
  await mockApi(page, {
    stream: sse([
      [
        "step",
        {
          index: 1,
          tool: "compare_documents",
          arguments: { question: "furto", documents: ["regulamento", "handbook"] },
          summary: "compared 2 documents",
          sources: [1],
          error: null,
          duration_ms: 900,
        },
      ],
      ["sources", { sources: [SOURCE] }],
      ["delta", { text: "Ambos indicam 24 horas [1]." }],
      [
        "done",
        {
          answer: "Ambos indicam 24 horas [1].",
          citations: [SOURCE],
          grounded: true,
          model: "qwen3.5:4b",
        },
      ],
      ["saved", { user_message_id: "u1", assistant_message_id: "a1" }],
    ]),
  });
  await page.goto("/");

  await page.getByRole("radio", { name: "Agent" }).click();
  await page.getByLabel("Ask a question about your documents").fill("Comparar prazos de furto");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Ambos indicam 24 horas")).toBeVisible();
  await expect(page.getByText(/Agent used 1 tool/)).toBeVisible();
});

test("unanswerable questions are flagged", async ({ page }) => {
  const answer = "Não encontrei informação sobre isso nos documentos.";
  await mockApi(page, {
    stream: sse([
      ["sources", { sources: [] }],
      ["delta", { text: answer }],
      ["done", { answer, citations: [], grounded: false, model: null }],
      ["saved", { user_message_id: "u1", assistant_message_id: "a1" }],
    ]),
  });
  await page.goto("/");

  await page.getByLabel("Ask a question about your documents").fill("Qual é a capital de França?");
  await page.keyboard.press("Enter");

  await expect(page.getByText(answer)).toBeVisible();
  await expect(page.getByText("Not found in your documents")).toBeVisible();
});

test("document library: list, upload and delete", async ({ page }) => {
  await mockApi(page, {
    documents: [
      documentFixture(),
      documentFixture({
        id: "doc-bad",
        filename: "scan.pdf",
        status: "failed",
        error: "The PDF has no extractable text (it may be a scanned image).",
      }),
    ],
  });
  await page.goto("/documents");

  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
  await expect(page.getByText("regulamento-teletrabalho.pdf")).toBeVisible();
  await expect(page.getByText("Failed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Process scan.pdf again" })).toBeVisible();

  await page.getByLabel("Choose files to upload").setInputFiles({
    name: "notas.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Notas\n\nReunião na quinta-feira."),
  });
  await expect(page.getByText("notas.md", { exact: true })).toBeVisible();
  await expect(page.getByText("Queued")).toBeVisible();

  await page.getByRole("button", { name: "Delete scan.pdf" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("scan.pdf")).toHaveCount(0);
});

test("keyboard users can skip to the content", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard navigation is a desktop concern");
  await mockApi(page);
  await page.goto("/documents");

  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page).toHaveURL(/#main$/);
});
