"use client";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="max-w-2xl mx-auto px-4 py-24 text-center">
      <h1 className="text-2xl font-bold mb-3">Something went wrong</h1>
      <p className="text-muted-foreground mb-6 text-sm">{error.message || "Unexpected error"}</p>
      <button onClick={reset} className="px-5 py-2.5 rounded-xl gradient-primary text-white font-medium">Try again</button>
    </div>
  );
}
