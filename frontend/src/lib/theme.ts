"use client";

import { useSyncExternalStore } from "react";

const KEY = "buywise_dark";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved !== null) return saved === "true";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => { listeners.delete(cb); window.removeEventListener("storage", cb); };
}

/** Dark-mode state backed by localStorage (server snapshot is always light). */
export function useTheme(): [boolean, () => void] {
  const dark = useSyncExternalStore(subscribe, read, () => false);
  const toggle = () => {
    try { localStorage.setItem(KEY, String(!dark)); } catch { /* ignore */ }
    listeners.forEach((l) => l());
  };
  return [dark, toggle];
}
