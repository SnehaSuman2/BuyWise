"use client";
import { useEffect, useState } from "react";
import HomeV1 from "./HomeV1";
import HomeV2 from "./HomeV2";
import { assignExperiment, type Assignment } from "@/lib/experiment";
import { track } from "@/lib/analytics";
export default function HomeExperiment() {
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (!active) return;
      setAssignment(assignExperiment());
      track("experiment_exposure");
    });
    return () => { active = false; };
  }, []);
  if (!assignment) return <div className="max-w-6xl mx-auto px-6 py-24 min-h-[650px]" role="status"><p className="text-sm text-muted-foreground">Getting your shopping tools ready…</p><div className="mt-6 h-24 max-w-xl rounded-2xl bg-muted animate-pulse" /></div>;
  return assignment.variant === "a" ? <HomeV1 /> : <HomeV2 />;
}
