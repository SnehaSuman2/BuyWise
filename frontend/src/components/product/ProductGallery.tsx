"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut, Images } from "lucide-react";

const PLACEHOLDER = "https://placehold.co/600x600/1a1a2e/e0e0e0?text=No+image";
const MAX_TILT_DEG = 7;

/**
 * The product's photographs, with a viewer.
 *
 * Every frame is a real photograph published by a shop that sells the item, so
 * a product carried by several retailers has several angles. Nothing here is
 * generated: a rendered view of a product nobody photographed would be an
 * invention, and inventing what a product looks like is no more acceptable
 * than inventing its price.
 *
 * The hero tilts a little under the cursor. That is presentation, not data, and
 * it is switched off for anyone who has asked for reduced motion and for touch,
 * where there is no cursor to follow.
 */
export default function ProductGallery({ images, name }: { images: string[]; name: string }) {
  const shots = images.filter(Boolean);
  const gallery = shots.length ? shots : [PLACEHOLDER];
  const [index, setIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const [tilt, setTilt] = useState<{ x: number; y: number } | null>(null);
  const [mayTilt, setMayTilt] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  const current = gallery[Math.min(index, gallery.length - 1)];
  const step = useCallback(
    (by: number) => {
      setZoomed(false);
      setIndex((i) => (i + by + gallery.length) % gallery.length);
    },
    [gallery.length],
  );

  // A cursor to follow, and no standing request to keep motion down.
  useEffect(() => {
    const quiet = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    const decide = () => setMayTilt(fine.matches && !quiet.matches);
    decide();
    quiet.addEventListener("change", decide);
    fine.addEventListener("change", decide);
    return () => {
      quiet.removeEventListener("change", decide);
      fine.removeEventListener("change", decide);
    };
  }, []);

  // While the viewer is open it owns the keyboard and the page must not scroll under it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      else if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setZoomed((z) => !z); }
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, step]);

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!mayTilt) return;
    const box = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - box.left) / box.width - 0.5;
    const py = (e.clientY - box.top) / box.height - 0.5;
    setTilt({ x: -py * MAX_TILT_DEG * 2, y: px * MAX_TILT_DEG * 2 });
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        className="aspect-square rounded-2xl overflow-hidden bg-muted/20 glass cursor-zoom-in"
        style={{ perspective: "1200px" }}
        onMouseMove={onMove}
        onMouseLeave={() => setTilt(null)}
        onClick={() => setOpen(true)}
        role="button"
        tabIndex={0}
        aria-label={`Open larger photographs of ${name}`}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(true); } }}
      >
        <img
          src={current}
          alt={name}
          className="w-full h-full object-cover"
          style={{
            transform: tilt
              ? `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) scale(1.04)`
              : "rotateX(0deg) rotateY(0deg) scale(1)",
            transition: tilt ? "transform 80ms linear" : "transform 400ms ease-out",
          }}
        />
      </div>

      {gallery.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          {gallery.map((src, i) => (
            <button
              key={src}
              type="button"
              onClick={() => setIndex(i)}
              aria-label={`Photograph ${i + 1} of ${gallery.length}`}
              aria-current={i === index}
              className={`w-14 h-14 rounded-lg overflow-hidden border-2 transition-colors ${i === index ? "border-indigo-500" : "border-transparent hover:border-border"}`}
            >
              <img src={src} alt="" className="w-full h-full object-cover" />
            </button>
          ))}
          <span className="text-[11px] text-muted-foreground flex items-center gap-1 ml-1">
            <Images className="w-3.5 h-3.5" /> {gallery.length} photos, each from a shop selling it
          </span>
        </div>
      )}

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-label={`Photographs of ${name}`}
          onClick={() => setOpen(false)}
        >
          <button
            ref={closeRef}
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="absolute top-4 right-4 p-3 rounded-xl bg-white/10 text-white hover:bg-white/20 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>

          {gallery.length > 1 && (
            <>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); step(-1); }}
                aria-label="Previous photograph"
                className="absolute left-4 p-3 rounded-xl bg-white/10 text-white hover:bg-white/20 transition-colors"
              >
                <ChevronLeft className="w-6 h-6" />
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); step(1); }}
                aria-label="Next photograph"
                className="absolute right-4 p-3 rounded-xl bg-white/10 text-white hover:bg-white/20 transition-colors"
              >
                <ChevronRight className="w-6 h-6" />
              </button>
            </>
          )}

          <img
            src={current}
            alt={name}
            onClick={(e) => { e.stopPropagation(); setZoomed((z) => !z); }}
            className={`max-h-[85vh] max-w-full object-contain transition-transform duration-300 ${zoomed ? "scale-[1.8] cursor-zoom-out" : "scale-100 cursor-zoom-in"}`}
          />

          <div className="absolute bottom-5 left-1/2 -translate-x-1/2 flex items-center gap-3 text-white/70 text-xs">
            <span className="flex items-center gap-1">{zoomed ? <ZoomOut className="w-3.5 h-3.5" /> : <ZoomIn className="w-3.5 h-3.5" />} click to {zoomed ? "shrink" : "zoom"}</span>
            {gallery.length > 1 && <span>{index + 1} of {gallery.length} · arrow keys to move</span>}
            <span>Esc to close</span>
          </div>
        </div>
      )}
    </div>
  );
}
