"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";
import type { AppMeta } from "./types";

interface MetaState { meta: AppMeta | null; loading: boolean; error: string | null }

const MetaContext = createContext<MetaState>({ meta: null, loading: true, error: null });

export function MetaProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<MetaState>({ meta: null, loading: true, error: null });
  useEffect(() => {
    let cancelled = false;
    api.meta()
      .then((meta) => { if (!cancelled) setState({ meta, loading: false, error: null }); })
      .catch((e: Error) => { if (!cancelled) setState({ meta: null, loading: false, error: e.message }); });
    return () => { cancelled = true; };
  }, []);
  return <MetaContext.Provider value={state}>{children}</MetaContext.Provider>;
}

export function useMeta() {
  return useContext(MetaContext);
}
