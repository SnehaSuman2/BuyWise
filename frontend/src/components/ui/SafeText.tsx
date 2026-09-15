/** Renders agent/AI text safely: paragraphs, **bold**, *italics* and numbered lines — no HTML injection. */
export default function SafeText({ text, className = "" }: { text: string; className?: string }) {
  const lines = text.split(/\r?\n/);
  return (
    <div className={`space-y-1.5 ${className}`}>
      {lines.map((line, i) => (line.trim() ? <p key={i} className="leading-relaxed">{renderInline(line)}</p> : <div key={i} className="h-1" />))}
    </div>
  );
}

function renderInline(line: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) parts.push(line.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    else parts.push(<em key={key++}>{token.slice(1, -1)}</em>);
    last = m.index + token.length;
  }
  if (last < line.length) parts.push(line.slice(last));
  return parts;
}
