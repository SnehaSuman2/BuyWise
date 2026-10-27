/** Homepage experiment. Preview traffic is excluded from GA. */
export const EXPERIMENT_ID = "homepage_v2_2026_10";
export type Assignment = { variant: "a" | "b"; preview: boolean; mode: string };
const KEY = `buywise:${EXPERIMENT_ID}`;
let current: Assignment | null = null;
export function experimentContext(): Assignment | null { return current; }
export function assignExperiment(): Assignment {
  if (current) return current;
  const mode = process.env.NEXT_PUBLIC_HOMEPAGE_EXPERIMENT === "ab" ? "ab" : "v2";
  const override = new URLSearchParams(window.location.search).get("variant");
  try {
    if (override === "reset") sessionStorage.removeItem(`${KEY}:preview`);
    if (override === "a" || override === "b") sessionStorage.setItem(`${KEY}:preview`, override);
    const preview = sessionStorage.getItem(`${KEY}:preview`);
    if (preview === "a" || preview === "b") return current = { variant: preview, preview: true, mode };
    const stored = localStorage.getItem(KEY);
    const variant = mode === "v2" ? "b" : stored === "a" || stored === "b" ? stored : crypto.getRandomValues(new Uint32Array(1))[0] % 2 ? "b" : "a";
    if (mode === "ab") localStorage.setItem(KEY, variant);
    return current = { variant, preview: false, mode };
  } catch {
    return current = { variant: "b", preview: true, mode };
  }
}
