import { useMemo } from "react";
import { Command as CommandIcon } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import type { AltaEvent, MvpStatus, SelectedEntity } from "@/lib/types";

type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  status: MvpStatus | null;
  events: AltaEvent[];
  onSelect: (entity: SelectedEntity) => void;
};

export function CommandPalette({
  open,
  onOpenChange,
  status,
  events,
  onSelect,
}: CommandPaletteProps) {
  const { domain, t } = useI18n();
  const searchable = useMemo(() => {
    if (!open || !status) return [];
    return [
      ...status.opportunities.map((item) => ({
        kind: "opportunity" as const,
        id: item.id,
        label: item.title,
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.agents.map((item) => ({
        kind: "run" as const,
        id: item.runId,
        label: domain(item.id),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.expressions.map((item) => ({
        kind: "expression" as const,
        id: item.id,
        label: domain(item.kind),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.shadowPositions.map((item) => ({
        kind: "position" as const,
        id: item.id,
        label: t("shadowPosition", { symbol: item.symbol }),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.candidates.map((item) => ({
        kind: "event" as const,
        id: item.id,
        label: item.title,
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.assessments.map((item) => ({
        kind: "event" as const,
        id: item.id,
        label: t("assessmentLabel", {
          assessor: domain(item.assessor),
          verdict: domain(item.verdict),
        }),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.discussions.map((item) => ({
        kind: "event" as const,
        id: item.id,
        label: domain(item.eventType),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...events.map((item) => ({
        kind: "event" as const,
        id: item.eventId,
        label: domain(item.eventType),
        summary: item as unknown as Record<string, unknown>,
      })),
    ];
  }, [domain, events, open, status, t]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="command-dialog">
        <DialogTitle className="sr-only">{t("findAnyRecord")}</DialogTitle>
        <Command>
          <CommandInput placeholder={t("searchRecords")} />
          <CommandList aria-label={t("suggestions")}>
            <CommandEmpty>{t("noMatchingRecord")}</CommandEmpty>
            <CommandGroup heading={t("records")}>
              {searchable.map((entity) => (
                <CommandItem
                  key={`${entity.kind}-${entity.id}`}
                  value={`${entity.label} ${entity.id}`}
                  onSelect={() => {
                    onSelect(entity);
                    onOpenChange(false);
                  }}
                >
                  <CommandIcon />
                  <span>{entity.label}</span>
                  <small>{domain(entity.kind)}</small>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
