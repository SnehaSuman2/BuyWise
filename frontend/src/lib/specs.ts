import type { ModelSpecs } from "@/lib/types";

export function storageLabel(gb: number): string {
  return gb >= 1024 && gb % 1024 === 0 ? `${gb / 1024}TB` : `${gb}GB`;
}

/** The one-line spec summary used on cards and the family header. */
export function specSummary(s: ModelSpecs): string[] {
  const parts: string[] = [];
  if (s.display_in) parts.push(`${s.display_in}" ${s.refresh_hz ? `${s.refresh_hz}Hz` : ""}`.trim());
  if (s.chip) parts.push(s.chip);
  if (s.ram_gb && s.ram_gb.length) parts.push(`${s.ram_gb.join("/")}GB RAM`);
  if (s.storage_gb?.length) parts.push(s.storage_gb.map(storageLabel).join("/"));
  if (s.main_camera_mp) parts.push(`${s.main_camera_mp}MP`);
  if (s.battery_mah) parts.push(`${s.battery_mah.toLocaleString("en-IN")} mAh`);
  return parts;
}

export function titleCase(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}
