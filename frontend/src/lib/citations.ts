// Turn "[1]" and "[2, 3]" markers into Markdown links the answer renderer shows as buttons.

const MARKER = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g;
export const CITE_PREFIX = "#cite-";

export function linkCitations(text: string, available: number): string {
  return text.replace(MARKER, (whole, group: string) => {
    const numbers = group
      .split(",")
      .map((part) => Number(part.trim()))
      .filter((n) => n >= 1 && n <= available);
    if (!numbers.length) return whole;
    return numbers.map((n) => `[${n}](${CITE_PREFIX}${n})`).join("");
  });
}

export function citationNumber(href: string | undefined): number | null {
  if (!href?.startsWith(CITE_PREFIX)) return null;
  const n = Number(href.slice(CITE_PREFIX.length));
  return Number.isInteger(n) && n > 0 ? n : null;
}

export function describeSource(source: { filename: string; page: number | null }): string {
  return source.page ? `${source.filename}, p. ${source.page}` : source.filename;
}
