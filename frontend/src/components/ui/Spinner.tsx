import { Loader2 } from "lucide-react";

export default function Spinner({ label = "Loading…", className = "" }: { label?: string; className?: string }) {
  return (
    <div className={`flex items-center gap-2 text-sm text-muted-foreground ${className}`} role="status" aria-live="polite">
      <Loader2 className="w-4 h-4 animate-spin" /> {label}
    </div>
  );
}
