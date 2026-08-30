import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function readableMindSummary(value?: string) {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as {
      recent?: Array<{ finding?: unknown }>;
    };
    const finding = parsed.recent?.find(
      (item) => typeof item.finding === "string" && item.finding.trim(),
    )?.finding;
    if (typeof finding === "string") return finding;
  } catch {
    // Older memory versions may be plain text and remain readable as-is.
  }
  return value;
}
