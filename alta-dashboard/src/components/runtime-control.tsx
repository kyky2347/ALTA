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
      <div className="runtime-control" aria-label="Research runtime controls">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="sm"
              disabled={disabled || running || busy}
              aria-label="Start research runtime"
              onClick={() => void execute("start")}
            >
              <Play data-icon="inline-start" />
              <span className="runtime-action-label">Start</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Start the installed shadow-research service
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon-sm"
              variant="ghost"
              disabled={disabled || !running || busy}
              aria-label="Restart research runtime"
              onClick={() => setConfirm("restart")}
            >
              <RotateCw
                className={pending === "restart" ? "animate-spin" : ""}
              />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Restart the research service</TooltipContent>
        </Tooltip>
        <Button
          size="sm"
          variant="destructive"
          disabled={disabled || !running || busy}
          aria-label="Stop research runtime"
          onClick={() => setConfirm("stop")}
        >
          <CirclePause data-icon="inline-start" />
          <span className="runtime-action-label">Stop</span>
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
                ? "Stop the research runtime?"
                : "Restart the research runtime?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "stop"
                ? "ALTA will stop its agent service, supervisor, PostgreSQL, and Redis. The local dashboard shell remains available so you can start it again."
                : "The autonomous service will restart and wait for readiness. No capital or broker path is available from this console."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => confirm && void execute(confirm)}>
              {confirm === "stop" ? "Stop safely" : "Restart"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
