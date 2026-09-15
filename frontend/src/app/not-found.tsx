import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-24 text-center">
      <h1 className="text-3xl font-bold mb-3">Page not found</h1>
      <p className="text-muted-foreground mb-6">The page you are looking for doesn&apos;t exist or has moved.</p>
      <Link href="/" className="px-5 py-2.5 rounded-xl gradient-primary text-white font-medium">Back to search</Link>
    </div>
  );
}
