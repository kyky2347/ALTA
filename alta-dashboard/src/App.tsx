import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  CircleDot,
  Command as CommandIcon,
  History,
  KeyRound,
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
import { DecisionLedger } from "@/components/decision-ledger";
import { CredentialsCenter } from "@/components/credentials-center";
import { DetailInspector } from "@/components/detail-inspector";
import { EventTimeline } from "@/components/event-timeline";
import { LanguageToggle } from "@/components/language-toggle";
import { OpportunityField } from "@/components/opportunity-field";
import { RuntimeControl } from "@/components/runtime-control";
import { ShadowBook } from "@/components/shadow-book";
import { StatusPill } from "@/components/status-pill";
import { SystemOverview } from "@/components/system-overview";
import { useAltaConsole } from "@/hooks/use-alta-console";
import { useI18n } from "@/lib/i18n";
import type { SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";

type View =
  | "field"
  | "ledger"
  | "overview"
  | "agents"
  | "shadow"
  | "credentials";

const navigation: Array<{ id: View; icon: typeof Activity }> = [
  { id: "field", icon: Radar },
  { id: "ledger", icon: History },
  { id: "overview", icon: LayoutDashboard },
  { id: "agents", icon: Bot },
  { id: "shadow", icon: ShieldCheck },
  { id: "credentials", icon: KeyRound },
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
  const { domain, relative, systemMessage, t } = useI18n();
  const consoleState = useAltaConsole();
  const {
    control,
    status,
    runtime,
    credentials,
    credentialsError,
    events,
    preview,
    loading,
    error,
    connection,
    retryNow,
    controlRuntime,
    refreshCredentials,
    setProviderCredential,
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
  }, [domain, events, status, t]);
  const localizedSelected = useMemo(
    () => relabelEntity(selected, domain, t),
    [domain, selected, t],
  );
  const activeSelected =
    localizedSelected ??
    searchable.find((item) => item.kind === "opportunity") ??
    null;

  async function handleAction(action: "start" | "stop" | "restart") {
    setActionError(null);
    try {
      await controlRuntime(action);
    } catch (reason) {
      setActionError(
        systemMessage(
          reason instanceof Error ? reason.message : t("controlFailed"),
        ) ?? t("controlFailed"),
      );
    }
  }

  if (loading) return <LoadingScreen />;
  if (error && !preview)
    return <ConnectionScreen error={error} state={connection.status} />;
  if (!control && !preview)
    return <ConnectionScreen error={connection.message} onRetry={retryNow} />;

  return (
    <div
      className={cn(
        "app-shell",
        !railOpen && "rail-collapsed",
        view === "credentials" && "configuration-mode",
      )}
    >
      <header className="topbar">
        <div className="brand-lockup">
          <img src="/alta-brand-logo.png" alt="" className="brand-logo" />
          <div>
            <strong>ALTA</strong>
            <small>{t("productSubtitle")}</small>
          </div>
        </div>
        <div className="topbar-center">
          {preview && (
            <Badge variant="outline" className="preview-badge">
              {t("syntheticPreview")}
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
            <CircleDot />
            {t("heartbeat", {
              time: relative(runtime?.config.lastHeartbeatAt),
            })}
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
                ? t("operationRunning", {
                    action: domain(control.operation.action),
                    phase: domain(control.operation.phase ?? t("working")),
                  })
                : control.operation.status === "completed"
                  ? t("operationComplete", {
                      action: domain(control.operation.action),
                    })
                  : t("operationFailed", {
                      action: domain(control.operation.action),
                    })}
            </span>
          )}
        </div>
        <div className="topbar-actions">
          <Button
            variant="outline"
            size="sm"
            className="command-button"
            aria-label={t("findAnything")}
            onClick={() => setCommandOpen(true)}
          >
            <Search data-icon="inline-start" />
            <span>{t("findAnything")}</span>
            <kbd>⌘K</kbd>
          </Button>
          <LanguageToggle />
          <RuntimeControl
            control={control}
            disabled={preview || connection.status !== "online"}
            onAction={handleAction}
          />
        </div>
      </header>

      <nav className="side-rail" aria-label={t("dashboardSections")}>
        <Button
          variant="ghost"
          size="icon"
          className="rail-toggle"
          aria-label={t("toggleNavigation")}
          onClick={() => setRailOpen((current) => !current)}
        >
          <PanelLeftClose />
        </Button>
        <div className="rail-nav">
          {navigation.map(({ id, icon: Icon }) => (
            <button
              className={cn("rail-item", view === id && "is-active")}
              key={id}
              onClick={() => setView(id)}
            >
              <Icon />
              <span>{viewNavigationLabel(id, t)}</span>
            </button>
          ))}
        </div>
        <div className="rail-safety">
          <ShieldCheck />
          <div>
            <strong>{t("researchOnly")}</strong>
            <span>{t("shadowEnvironment")}</span>
            <span>{t("capitalDisabled")}</span>
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
            <AlertTitle>{t("lifecycleRejected")}</AlertTitle>
            <AlertDescription>{systemMessage(actionError)}</AlertDescription>
            <AlertAction>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActionError(null)}
              >
                {t("dismiss")}
              </Button>
            </AlertAction>
          </Alert>
        )}
        {historyError && view === "ledger" && (
          <Alert className="console-alert">
            <History />
            <AlertTitle>{t("olderHistoryUnavailable")}</AlertTitle>
            <AlertDescription>
              {systemMessage(historyError)} {t("liveSyncContinues")}
            </AlertDescription>
          </Alert>
        )}
        <div className="workspace-heading">
          <div>
            <h1>{viewHeading(view, t)}</h1>
          </div>
          <div className="workspace-context">
            <span>{domain(status?.environment ?? "shadow")}</span>
            <Separator orientation="vertical" />
            <span>{status?.currentPipelineId ?? t("noActiveCycle")}</span>
            <Separator orientation="vertical" />
            <span>
              {runtime?.config.nextCycleAt
                ? t("nextCycle", {
                    time: relative(runtime.config.nextCycleAt),
                  })
                : t("scheduleUnavailable")}
            </span>
          </div>
        </div>

        {view === "credentials" ? (
          <CredentialsCenter
            inventory={credentials}
            error={credentialsError}
            runtimeActive={Boolean(
              control?.runtime.ready ||
                control?.runtime.host?.processAlive ||
                control?.runtime.supervisor?.childProcessAlive ||
                control?.operation?.status === "running",
            )}
            preview={preview}
            onRefresh={refreshCredentials}
            onSave={setProviderCredential}
          />
        ) : !status ? (
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

      {view !== "credentials" && (
        <DetailInspector
          selected={activeSelected}
          status={status}
          preview={preview}
        />
      )}

      <Dialog open={commandOpen} onOpenChange={setCommandOpen}>
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
                      setSelected(entity);
                      setCommandOpen(false);
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
    </div>
  );
}

function LoadingScreen() {
  const { t } = useI18n();
  return (
    <div className="full-screen-state">
      <div className="state-language-toggle">
        <LanguageToggle />
      </div>
      <div className="loading-brand">
        <img src="/alta-brand-logo.png" alt="" />
        <strong>ALTA</strong>
      </div>
      <div className="loading-skeletons" aria-hidden="true">
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
      <h1>{t("openingConsole")}</h1>
      <p>{t("openingConsoleDetail")}</p>
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
  const { systemMessage, t } = useI18n();
  const protectedLaunch = state === "unauthorized";
  const incompatible = state === "incompatible";
  return (
    <div className="full-screen-state">
      <div className="state-language-toggle">
        <LanguageToggle />
      </div>
      {protectedLaunch || incompatible ? <ShieldCheck /> : <WifiOff />}
      <h1>
        {protectedLaunch
          ? t("secureLaunchRequired")
          : incompatible
            ? t("dashboardUpdateRequired")
            : t("reconnectingLocalService")}
      </h1>
      <p>
        {protectedLaunch
          ? t("secureLaunchHelp")
          : (systemMessage(error) ?? t("automaticRecovery"))}
      </p>
      {protectedLaunch || incompatible ? (
        <code>{incompatible ? "./alta dashboard" : "./alta dashboard"}</code>
      ) : (
        <Button onClick={onRetry}>
          <RefreshCw data-icon="inline-start" /> {t("retryNow")}
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
  const { relative, systemMessage, t } = useI18n();
  if (connection.status === "online" && !connection.stale) return null;
  const stoppedSnapshot = connection.status === "online" && !runtimeReady;
  return (
    <Alert className="console-alert connection-alert">
      {stoppedSnapshot ? <ShieldCheck /> : <WifiOff />}
      <AlertTitle>
        {stoppedSnapshot
          ? t("runtimeStoppedSnapshot")
          : connection.status === "connecting"
            ? t("reconnecting")
            : t("liveSyncDegraded")}
      </AlertTitle>
      <AlertDescription>
        {systemMessage(connection.message) ?? t("restoringConnection")}
        {connection.lastSuccessfulAt && (
          <>
            {" "}
            {t("lastSynchronized", {
              time: relative(connection.lastSuccessfulAt),
            })}
          </>
        )}
      </AlertDescription>
      {!stoppedSnapshot && (
        <AlertAction>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw data-icon="inline-start" /> {t("retry")}
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
  const { t } = useI18n();
  return (
    <section className="stopped-state">
      <span>
        <Activity />
      </span>
      <h2>{active ? t("runtimeRecoveringTitle") : t("operatorShellReady")}</h2>
      <p>
        {active
          ? t("runtimeRecoveringDetail")
          : installed
            ? t("runtimeInstalledDetail")
            : t("runtimeInstallDetail")}
      </p>
      <Button size="lg" disabled={active || disabled} onClick={onStart}>
        {active ? t("restoringReadiness") : t("startResearchRuntime")}
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
  const { domain, number, t } = useI18n();
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
                label: domain(agent.id),
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
            <h2>{domain(agent.id)}</h2>
            <p>{mind?.rollingSummary ?? t("noRollingSummary")}</p>
            <div className="desk-facts">
              <span>
                {t("model")}
                <strong>{agent.modelId ?? agent.modelProvider ?? "—"}</strong>
              </span>
              <span>
                {t("turns")}
                <strong>{mind?.turnCount ?? "—"}</strong>
              </span>
              <span>
                {t("context")}
                <strong>{number(mind?.contextTokens)}</strong>
              </span>
            </div>
          </button>
        );
      })}
    </section>
  );
}

function viewNavigationLabel(view: View, t: ReturnType<typeof useI18n>["t"]) {
  if (view === "field") return t("liveField");
  if (view === "ledger") return t("decisionLedger");
  if (view === "overview") return t("systemOverview");
  if (view === "agents") return t("agentDesk");
  if (view === "shadow") return t("shadowBook");
  return t("credentials");
}

function viewHeading(view: View, t: ReturnType<typeof useI18n>["t"]) {
  if (view === "field") return t("firmInMotion");
  if (view === "ledger") return t("everyDecisionTrail");
  if (view === "overview") return t("operatingPosture");
  if (view === "agents") return t("specializedMinds");
  if (view === "shadow") return t("auditedShadowExpressions");
  return t("secureProviderConfiguration");
}

function relabelEntity(
  entity: SelectedEntity | null,
  domain: ReturnType<typeof useI18n>["domain"],
  t: ReturnType<typeof useI18n>["t"],
) {
  if (!entity) return null;
  const summary = entity.summary ?? {};
  if (entity.kind === "opportunity")
    return { ...entity, label: String(summary.title ?? entity.label) };
  if (entity.kind === "run")
    return {
      ...entity,
      label: domain(String(summary.id ?? summary.role ?? entity.label)),
    };
  if (entity.kind === "expression")
    return { ...entity, label: domain(String(summary.kind ?? entity.label)) };
  if (entity.kind === "position")
    return {
      ...entity,
      label: t("shadowPosition", {
        symbol: String(summary.symbol ?? entity.label.split(" ")[0]),
      }),
    };
  const eventType = summary.eventType;
  return typeof eventType === "string"
    ? { ...entity, label: domain(eventType) }
    : entity;
}
