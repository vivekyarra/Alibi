// R5: forbidden claims must not appear in UI source (mirrors scripts/claims_lint.py).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const FORBIDDEN = [
  "cryptographic",
  "impossible to fake",
  "detects all deepfakes",
  "100% accurate",
  "proves the video is fake",
  "guaranteed",
];
const ALLOWED = ["not cryptographic proof", "not a cryptographic proof", "is not cryptographic"];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

describe("claims lint (R5)", () => {
  const root = resolve(__dirname, "..");
  const targets = [...files(join(root, "src")), join(root, "index.html")];
  it.each(targets)("%s has no forbidden claims", (f) => {
    const hits: string[] = [];
    readFileSync(f, "utf-8")
      .split("\n")
      .forEach((line, i) => {
        let low = line.toLowerCase();
        for (const a of ALLOWED) low = low.split(a).join("");
        for (const p of FORBIDDEN) if (low.includes(p)) hits.push(`${i + 1}: ${p}`);
      });
    expect(hits).toEqual([]);
  });
});
