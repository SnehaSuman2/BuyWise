"use client";

import { useEffect, useRef, useState } from "react";
import { useMeta } from "@/lib/meta";

declare global {
  interface Window {
    google?: { accounts: { id: { initialize: (cfg: { client_id: string; callback: (r: { credential: string }) => void }) => void; renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void } } };
  }
}

/** Google Identity Services button. Renders nothing unless GOOGLE_CLIENT_ID is configured on the backend. */
export default function GoogleSignInButton({ onCredential }: { onCredential: (idToken: string) => void }) {
  const { meta } = useMeta();
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || null;
  const enabled = Boolean(meta?.google_auth_enabled && clientId);
  const callbackRef = useRef(onCredential);
  useEffect(() => { callbackRef.current = onCredential; }, [onCredential]);

  useEffect(() => {
    if (!enabled) return;
    const existing = document.getElementById("google-gsi");
    const init = () => {
      if (!window.google || !ref.current || !clientId) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => callbackRef.current(r.credential) });
      window.google.accounts.id.renderButton(ref.current, { theme: "outline", size: "large", width: 320, text: "continue_with" });
      setReady(true);
    };
    if (existing) { init(); return; }
    const s = document.createElement("script");
    s.id = "google-gsi";
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = init;
    document.head.appendChild(s);
  }, [enabled, clientId]);

  if (!enabled) return null;
  return (
    <div className="flex flex-col items-center gap-2">
      <div ref={ref} className="min-h-10" />
      {!ready && <span className="text-xs text-muted-foreground">Loading Google sign-in…</span>}
    </div>
  );
}
