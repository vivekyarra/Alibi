// WCAG 2.1 AA contrast check of the theme color tokens in src/styles.css (light and dark).
// jsdom has no layout engine, so axe cannot measure contrast; this test checks the tokens directly.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "../../src/styles.css"), "utf-8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const vars: Record<string, string> = {};
  for (const m of css.slice(open + 1, close).matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    vars[m[1]] = m[2];
  }
  return vars;
}

function luminance(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

function ratio(a: string, b: string): number {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// [foreground, background, minimum ratio]. Text pairs need 4.5; UI component boundaries need 3.
const PAIRS: [string, string, number][] = [
  ["text", "bg", 4.5],
  ["text", "surface", 4.5],
  ["muted", "bg", 4.5],
  ["muted", "surface", 4.5],
  ["link", "bg", 4.5],
  ["link", "surface", 4.5],
  ["error", "bg", 4.5],
  ["error", "surface", 4.5],
  ["button-text", "button-bg", 4.5],
  ["verified-text", "verified-bg", 4.5],
  ["contradicted-text", "contradicted-bg", 4.5],
  ["inconclusive-text", "inconclusive-bg", 4.5],
  ["text", "verified-bg", 4.5],
  ["text", "contradicted-bg", 4.5],
  ["text", "inconclusive-bg", 4.5],
  ["link", "inconclusive-bg", 4.5],
  ["muted", "inconclusive-bg", 4.5],
  ["pending-text", "pending-bg", 4.5],
  ["bg", "contradicted-text", 4.5],
  ["border", "bg", 3],
  ["border", "surface", 3],
  ["focus", "bg", 3],
  ["focus", "surface", 3],
];

describe.each([
  ["light", ":root {"],
  ["dark (prefers-color-scheme)", ':root:not([data-theme="light"])'],
  ["dark (toggle)", ':root[data-theme="dark"]'],
])("%s theme contrast", (_name, selector) => {
  const vars = block(selector);
  it.each(PAIRS)("%s on %s meets the minimum ratio", (fg, bg, min) => {
    expect(vars[fg], `missing --${fg}`).toBeDefined();
    expect(vars[bg], `missing --${bg}`).toBeDefined();
    expect(ratio(vars[fg], vars[bg])).toBeGreaterThanOrEqual(min);
  });
});
