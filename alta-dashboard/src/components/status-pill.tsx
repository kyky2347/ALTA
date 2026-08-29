import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function StatusPill({
  status,
  live = false,
}: {
  status: string;
  live?: boolean;
}) {
  const healthy = /ready|running|healthy|complete|validated|open|waiting/i.test(
    status,
  );
  const failed = /fail|error|degraded|reject|stopped/i.test(status);
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 gap-1.5 rounded-full border-black/8 bg-white/75 px-2 text-[10px] font-semibold tracking-[0.08em] uppercase shadow-none",
        failed && "text-rose-700",
        healthy && !failed && "text-emerald-800",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full bg-current",
          live && healthy && "motion-safe:animate-pulse",
        )}
      />
      {status.replaceAll("_", " ")}
    </Badge>
  );
}
