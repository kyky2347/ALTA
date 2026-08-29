import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  CircleDot,
  Command as CommandIcon,
  History,
  LayoutDashboard,
  PanelLeftClose,
  Radar,
  Search,
  ShieldCheck,
  TriangleAlert,
  WifiOff,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DecisionLedger } from "@/components/decision-ledger";
import { DetailInspector } from "@/components/detail-inspector";
import { EventTimeline } from "@/components/event-timeline";
import { OpportunityField } from "@/components/opportunity-field";
import { RuntimeControl } from "@/components/runtime-control";
import { ShadowBook } from "@/components/shadow-book";
import { StatusPill } from "@/components/status-pill";
import { SystemOverview } from "@/components/system-overview";
import { useAltaConsole } from "@/hooks/use-alta-console";
import { relativeTime, titleCase } from "@/lib/display";
import type { SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";

type View = "field" | "ledger" | "overview" | "agents" | "shadow";

const navigation: Array<{ id: View; label: string; icon: typeof Activity }> = [
  { id: "field", label: "Live field", icon: Radar },
  { id: "ledger", label: "Decision ledger", icon: History },
  { id: "overview", label: "System overview", icon: LayoutDashboard },
  { id: "agents", label: "Agent desk", icon: Bot },
  { id: "shadow", label: "Shadow book", icon: ShieldCheck },
];

function storedView(): View {
  try {
    const value = window.localStorage.getItem("alta.console.view");
    return navigation.some((item) => item.id === value)
      ? (value as View)
      : "field";
  } catch {
    return "field";
  }
}

function storedRail() {
  try {
    return window.localStorage.getItem("alta.console.rail") !== "closed";
  } catch {
    return true;
  }
}

export default function App() {
  const consoleState = useAltaConsole();
  const {
    control,
    status,
    runtime,
    events,
    preview,
    loading,
    error,
    connection,
    retryNow,
    controlRuntime,
    loadOlderEvents,
    loadingOlder,
    historyError,
    hasOlder,
  } = consoleState;
  const [view, setView] = useState<View>(storedView);
  const [selected, setSelected] = useState<SelectedEntity | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(storedRail);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((current) => !current);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("alta.console.view", view);
      window.localStorage.setItem(
        "alta.console.rail",
        railOpen ? "open" : "closed",
      );
    } catch {
      // Browser storage is optional; the operator console remains functional.
    }
  }, [railOpen, view]);

  const searchable = useMemo(() => {
    if (!status) return [];
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
        label: titleCase(item.id),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.expressions.map((item) => ({
        kind: "expression" as const,
        id: item.id,
        label: titleCase(item.kind),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.shadowPositions.map((item) => ({
        kind: "position" as const,
        id: item.id,
        label: `${item.symbol} shadow position`,
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
        label: `${titleCase(item.assessor)} assessment · ${item.verdict}`,
        summary: item as unknown as Record<string, unknown>,
      })),
      ...status.discussions.map((item) => ({
        kind: "event" as const,
        id: item.id,
        label: titleCase(item.eventType),
        summary: item as unknown as Record<string, unknown>,
      })),
      ...events.map((item) => ({
        kind: "event" as const,
        id: item.eventId,
        label: titleCase(item.eventType),
        summary: item as unknown as Record<string, unknown>,
      })),
    ];
  }, [events, status]);
  const activeSelected =
    selected ?? searchable.find((item) => item.kind === "opportunity") ?? null;

  async function handleAction(action: "start" | "stop" | "restart") {
    setActionError(null);
    try {
      await controlRuntime(action);
    } catch (reason) {
      setActionError(
        reason instanceof Error ? reason.message : "Control action failed",
      );
    }
  }

  if (loading) return <LoadingScreen />;
  if (error && !preview)
    return <ConnectionScreen error={error} state={connection.status} />;
  if (!control && !preview)
    return <ConnectionScreen error={connection.message} onRetry={retryNow} />;

  return (
    <TooltipProvider delayDuration={300}>
      <div className={cn("app-shell", !railOpen && "rail-collapsed")}>
        <header className="topbar">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <div>
              <strong>ALTA</strong>
              <small>Autonomous LLM Trading Asterism</small>
            </div>
          </div>
          <div className="topbar-center">
            {preview && (
              <Badge variant="outline" className="preview-badge">
                Synthetic preview
              </Badge>
            )}
            <StatusPill
              status={
                connection.status === "online"
                  ? control?.runtime.ready
                    ? "runtime ready"
                    : control?.runtime.host?.processAlive ||
                        control?.runtime.supervisor?.childProcessAlive
                      ? "runtime recovering"
                      : "runtime stopped"
                  : "console reconnecting"
              }
              live
            />
            <span className="heartbeat">
              <CircleDot /> Heartbeat{" "}
              {relativeTime(runtime?.config.lastHeartbeatAt)}
            </span>
            {control?.operation && (
              <span
                className={cn(
                  "operation-progress",
                  `is-${control.operation.status}`,
                )}
                role="status"
                aria-live="polite"
                title={control.operation.error}
              >
                {control.operation.status === "running" ? (
                  <span className="loading-orbit" />
                ) : control.operation.status === "completed" ? (
                  <CheckCircle2 />
                ) : (
                  <TriangleAlert />
                )}
                {control.operation.status === "running"
                  ? `${titleCase(control.operation.action)} · ${titleCase(control.operation.phase ?? "working")}`
                  : control.operation.status === "completed"
                    ? `${titleCase(control.operation.action)} complete`
                    : `${titleCase(control.operation.action)} failed · retry from controls`}
              </span>
            )}
          </div>
          <div className="topbar-actions">
            <Button
              variant="outline"
              size="sm"
              className="command-button"
              onClick={() => setCommandOpen(true)}
            >
              <Search data-icon="inline-start" />
              <span>Find anything</span>
              <kbd>⌘K</kbd>
            </Button>
            <RuntimeControl
              control={control}
              disabled={preview || connection.status !== "online"}
              onAction={handleAction}
            />
          </div>
        </header>

        <nav className="side-rail" aria-label="Dashboard sections">
          <Button
            variant="ghost"
            size="icon"
            className="rail-toggle"
            aria-label="Toggle navigation rail"
            onClick={() => setRailOpen((current) => !current)}
          >
            <PanelLeftClose />
          </Button>
          <div className="rail-nav">
            {navigation.map(({ id, label, icon: Icon }) => (
              <button
                className={cn("rail-item", view === id && "is-active")}
                key={id}
                onClick={() => setView(id)}
              >
                <Icon />
                <span>{label}</span>
              </button>
            ))}
          </div>
          <div className="rail-safety">
            <ShieldCheck />
            <div>
              <strong>Research only</strong>
              <span>Shadow environment</span>
              <span>Capital disabled</span>
            </div>
          </div>
        </nav>

        <main className="workspace">
          <ConnectionBanner
            connection={connection}
            runtimeReady={Boolean(control?.runtime.ready)}
            onRetry={retryNow}
          />
          {actionError && (
            <Alert variant="destructive" className="console-alert">
              <TriangleAlert />
              <AlertTitle>Lifecycle action was not accepted</AlertTitle>
              <AlertDescription>{actionError}</AlertDescription>
              <AlertAction>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActionError(null)}
                >
                  Dismiss
                </Button>
              </AlertAction>
            </Alert>
          )}
          {historyError && view === "ledger" && (
            <Alert className="console-alert">
              <History />
              <AlertTitle>Older history is temporarily unavailable</AlertTitle>
              <AlertDescription>
                {historyError} Live synchronization continues independently.
              </AlertDescription>
            </Alert>
          )}
          <div className="workspace-heading">
            <div>
              <h1>
                {view === "field"
                  ? "The firm, in motion"
                  : view === "ledger"
                    ? "Every decision leaves a trail"
                    : view === "overview"
                      ? "Operating posture"
                      : view === "agents"
                        ? "Specialized minds"
                        : "Audited shadow expressions"}
              </h1>
            </div>
            <div className="workspace-context">
              <span>{status?.environment ?? "shadow"}</span>
              <Separator orientation="vertical" />
              <span>{status?.currentPipelineId ?? "No active cycle"}</span>
              <Separator orientation="vertical" />
              <span>
                {runtime?.config.nextCycleAt
                  ? `Next cycle ${relativeTime(runtime.config.nextCycleAt)}`
                  : "Schedule unavailable"}
              </span>
            </div>
          </div>

          {!status ? (
            <StoppedState
              installed={control?.runtime.installed ?? false}
              active={Boolean(
                control?.runtime.host?.processAlive ||
                  control?.runtime.supervisor?.childProcessAlive,
              )}
              disabled={connection.status !== "online"}
              onStart={() => void handleAction("start")}
            />
          ) : (
            <>
              {view === "field" && (
                <OpportunityField
                  status={status}
                  runtime={runtime}
                  selected={activeSelected}
                  onSelect={setSelected}
                />
              )}
              {view === "ledger" && (
                <DecisionLedger
                  events={events}
                  status={status}
                  selected={activeSelected}
                  onSelect={setSelected}
                  onLoadOlder={loadOlderEvents}
                  loadingOlder={loadingOlder}
                  hasOlder={preview ? false : hasOlder}
                />
              )}
              {view === "overview" && (
                <SystemOverview
                  status={status}
                  runtime={runtime}
                  onSelect={setSelected}
                />
              )}
              {view === "agents" && (
                <AgentDesk
                  status={status}
                  runtime={runtime}
                  onSelect={setSelected}
                />
              )}
              {view === "shadow" && (
                <ShadowBook
                  status={status}
                  runtime={runtime}
                  onSelect={setSelected}
                />
              )}
              <EventTimeline events={events} onSelect={setSelected} />
            </>
          )}
        </main>

        <DetailInspector
          selected={activeSelected}
          status={status}
          preview={preview}
        />

        <Dialog open={commandOpen} onOpenChange={setCommandOpen}>
          <DialogContent className="command-dialog">
            <DialogTitle className="sr-only">Find any ALTA record</DialogTitle>
            <Command>
              <CommandInput placeholder="Search opportunities, agents, expressions, positions…" />
              <CommandList>
                <CommandEmpty>No matching durable record.</CommandEmpty>
                <CommandGroup heading="Records">
                  {searchable.map((entity) => (
                    <CommandItem
                      key={`${entity.kind}-${entity.id}`}
                      value={`${entity.label} ${entity.id}`}
                      onSelect={() => {
                        setSelected(entity);
                        setCommandOpen(false);
                      }}
                    >
                      <CommandIcon />
                      <span>{entity.label}</span>
                      <small>{entity.kind}</small>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  );
}

function LoadingScreen() {
  return (
    <div className="full-screen-state">
      <span className="brand-mark is-large">
        <span />
        <span />
        <span />
      </span>
      <div className="loading-skeletons" aria-hidden="true">
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
      <h1>Opening the operator console</h1>
      <p>Establishing a local, authenticated view of the research runtime.</p>
    </div>
  );
}
function ConnectionScreen({
  error,
  state,
  onRetry,
}: {
  error: string | null;
  state?: ReturnType<typeof useAltaConsole>["connection"]["status"];
  onRetry?: () => void;
}) {
  const protectedLaunch = state === "unauthorized";
  const incompatible = state === "incompatible";
  return (
    <div className="full-screen-state">
      {protectedLaunch || incompatible ? <ShieldCheck /> : <WifiOff />}
      <h1>
        {protectedLaunch
          ? "This console needs its secure launch URL"
          : incompatible
            ? "Dashboard update required"
            : "Reconnecting to the local operator service"}
      </h1>
      <p>
        {protectedLaunch
          ? "Run ./alta dashboard and open the one-time local URL printed in the terminal."
          : (error ??
            "The page will recover automatically when the local service is available.")}
      </p>
      {protectedLaunch || incompatible ? (
        <code>
          {incompatible
            ? "pnpm dashboard:build && ./alta dashboard"
            : "./alta dashboard"}
        </code>
      ) : (
        <Button onClick={onRetry}>
          <RefreshCw data-icon="inline-start" /> Retry now
        </Button>
      )}
    </div>
  );
}

function ConnectionBanner({
  connection,
  runtimeReady,
  onRetry,
}: {
  connection: ReturnType<typeof useAltaConsole>["connection"];
  runtimeReady: boolean;
  onRetry: () => void;
}) {
  if (connection.status === "online" && !connection.stale) return null;
  const stoppedSnapshot = connection.status === "online" && !runtimeReady;
  return (
    <Alert className="console-alert connection-alert">
      {stoppedSnapshot ? <ShieldCheck /> : <WifiOff />}
      <AlertTitle>
        {stoppedSnapshot
          ? "Runtime stopped · saved browser snapshot"
          : connection.status === "connecting"
            ? "Reconnecting"
            : "Live synchronization is degraded"}
      </AlertTitle>
      <AlertDescription>
        {connection.message ?? "ALTA is restoring the live connection."}
        {connection.lastSuccessfulAt && (
          <> Last synchronized {relativeTime(connection.lastSuccessfulAt)}.</>
        )}
      </AlertDescription>
      {!stoppedSnapshot && (
        <AlertAction>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw data-icon="inline-start" /> Retry
          </Button>
        </AlertAction>
      )}
    </Alert>
  );
}
function StoppedState({
  installed,
  active,
  disabled,
  onStart,
}: {
  installed: boolean;
  active: boolean;
  disabled: boolean;
  onStart: () => void;
}) {
  return (
    <section className="stopped-state">
      <span>
        <Activity />
      </span>
      <h2>
        {active
          ? "The research runtime is recovering."
          : "The operator shell is ready."}
      </h2>
      <p>
        {active
          ? "ALTA is bootstrapping dependencies or restoring readiness. Controls remain locked until this transition settles."
          : installed
            ? "Start the installed service to resume autonomous discovery, committee review, audited expression, and shadow observation."
            : "Install the ALTA service from the terminal before starting it from this console."}
      </p>
      <Button
        size="lg"
        disabled={!installed || active || disabled}
        onClick={onStart}
      >
        {active ? "Restoring readiness…" : "Start research runtime"}
      </Button>
    </section>
  );
}

function AgentDesk({
  status,
  runtime,
  onSelect,
}: {
  status: NonNullable<ReturnType<typeof useAltaConsole>["status"]>;
  runtime: ReturnType<typeof useAltaConsole>["runtime"];
  onSelect: (entity: SelectedEntity) => void;
}) {
  return (
    <section className="desk-grid">
      {status.agents.map((agent) => {
        const mind = runtime?.minds.find((item) => item.id === agent.id);
        return (
          <button
            className="desk-card"
            key={agent.runId}
            onClick={() =>
              onSelect({
                kind: "run",
                id: agent.runId,
                label: titleCase(agent.id),
                summary: agent as unknown as Record<string, unknown>,
              })
            }
          >
            <div className="desk-card-top">
              <span>
                <Bot />
              </span>
              <StatusPill status={agent.status} live />
            </div>
            <h2>{titleCase(agent.id)}</h2>
            <p>
              {mind?.rollingSummary ??
                "No durable rolling summary is available for this agent role."}
            </p>
            <div className="desk-facts">
              <span>
                Model
                <strong>{agent.modelId ?? agent.modelProvider ?? "—"}</strong>
              </span>
              <span>
                Turns<strong>{mind?.turnCount ?? "—"}</strong>
              </span>
              <span>
                Context
                <strong>{mind?.contextTokens?.toLocaleString() ?? "—"}</strong>
              </span>
            </div>
          </button>
        );
      })}
    </section>
  );
}
