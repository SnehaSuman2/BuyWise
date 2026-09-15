import { AlertTriangle } from "lucide-react";

export default function ErrorBox({ message, className = "" }: { message: string; className?: string }) {
  return (
    <div className={`p-3 rounded-xl bg-rose-500/10 text-rose-600 text-sm border border-rose-500/20 flex gap-2 ${className}`} role="alert">
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{message}</span>
    </div>
  );
}
