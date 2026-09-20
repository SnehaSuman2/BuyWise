/** Helpers for search-by-photo, shared by the home page and the search page. */

/** Session-storage key the home page uses to hand a chosen photo to the search page. */
export const PENDING_PHOTO_KEY = "buywise_pending_photo";

/**
 * Shrink a photo in the browser before upload. A phone camera shot is 3–8 MB; Google
 * Lens needs nothing like that, and the API caps uploads at 5 MB. Longest side 1024px,
 * JPEG at 0.85, which lands around 150–300 KB.
 */
export async function downscaleImage(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not process the image");
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}
