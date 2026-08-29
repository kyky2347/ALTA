import { useState } from "react";
import { CirclePause, Play, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ControlState } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

type Action = "start" | "stop" | "restart";

export function RuntimeControl({
  control,
  disabled,
  onAction,
}: {
  control: ControlState | null;
  disabled?: boolean;
  onAction: (action: Action) => Promise<void>;
}) {
  const { t } = useI18n();
  const [pending, setPending] = useState<Action | null>(null);
  const [confirm, setConfirm] = useState<Action | null>(null);
  const running = Boolean(
    control?.runtime.ready ||
      control?.runtime.host?.processAlive ||
      control?.runtime.supervisor?.childProcessAlive,
  );
  const busy = control?.operation?.status === "running" || pending !== null;

  async function execute(action: Action) {
    setConfirm(null);
    setPending(action);
    try {
      await onAction(action);
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <div className="runtime-control" aria-label={t("runtimeControls")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="sm"
              disabled={disabled || running || busy}
              aria-label={t("startRuntimeAria")}
              onClick={() => void execute("start")}
            >
              <Play data-icon="inline-start" />
              <span className="runtime-action-label">{t("start")}</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("startRuntimeTip")}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon-sm"
              variant="ghost"
              disabled={disabled || !running || busy}
              aria-label={t("restartRuntimeAria")}
              onClick={() => setConfirm("restart")}
            >
              <RotateCw
                className={pending === "restart" ? "animate-spin" : ""}
              />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("restartRuntimeTip")}</TooltipContent>
        </Tooltip>
        <Button
          size="sm"
          variant="destructive"
          disabled={disabled || !running || busy}
          aria-label={t("stopRuntimeAria")}
          onClick={() => setConfirm("stop")}
        >
          <CirclePause data-icon="inline-start" />
          <span className="runtime-action-label">{t("stop")}</span>
        </Button>
      </div>
      <AlertDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm === "stop"
                ? t("stopRuntimeConfirm")
                : t("restartRuntimeConfirm")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "stop"
                ? t("stopRuntimeDetail")
                : t("restartRuntimeDetail")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => confirm && void execute(confirm)}>
              {confirm === "stop" ? t("stopSafely") : t("restart")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
