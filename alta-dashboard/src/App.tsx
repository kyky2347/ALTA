import {
  lazy,
  startTransition,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  CircleDot,
  History,
  KeyRound,
  Landmark,
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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { EventTimeline } from "@/components/event-timeline";
import { OperatingBrief } from "@/components/operating-brief";
import { AgentDesk } from "@/components/agent-desk";
import { LanguageToggle } from "@/components/language-toggle";
import { BrandLockup } from "@/components/brand-lockup";
import { AgentModelSettings } from "@/components/agent-model-settings";
import { RuntimeControl } from "@/components/runtime-control";
import { StatusPill } from "@/components/status-pill";
import { useAltaConsole } from "@/hooks/use-alta-console";
import { useI18n } from "@/lib/i18n";
import {
  latestRankLeader,
  opportunityIdForEntity,
  refreshSelectedEntity,
} from "@/lib/opportunity-selection";
import type { ControlState, SelectedEntity } from "@/lib/types";
import { cn } from "@/lib/utils";
import { runtimeSchedule } from "@/lib/runtime-schedule";

type View =
  | "field"
  | "ledger"
  | "overview"
  | "agents"
  | "shadow"
  | "capital"
  | "credentials";

const navigation: Array<{ id: View; icon: typeof Activity }> = [
  { id: "field", icon: Radar },
  { id: "ledger", icon: History },
  { id: "overview", icon: LayoutDashboard },
  { id: "agents", icon: Bot },
  { id: "shadow", icon: ShieldCheck },
  { id: "capital", icon: Landmark },
  { id: "credentials", icon: KeyRound },
];

const viewLoaders = {
  field: () => import("@/components/opportunity-field"),
  ledger: () => import("@/components/decision-ledger"),
  overview: () => import("@/components/system-overview"),
  shadow: () => import("@/components/shadow-book"),
  capital: () => import("@/components/capital-console"),
  credentials: () => import("@/components/credentials-center"),
};
const loadCommandPalette = () => import("@/components/command-palette");
const loadDetailInspector = () => import("@/components/detail-inspector");
const OpportunityField = lazy(async () => ({
  default: (await viewLoaders.field()).OpportunityField,
}));
const DecisionLedger = lazy(async () => ({
  default: (await viewLoaders.ledger()).DecisionLedger,
}));
const SystemOverview = lazy(async () => ({
  default: (await viewLoaders.overview()).SystemOverview,
}));
const ShadowBook = lazy(async () => ({
  default: (await viewLoaders.shadow()).ShadowBook,
}));
const CapitalConsole = lazy(async () => ({
  default: (await viewLoaders.capital()).CapitalConsole,
}));
const CredentialsCenter = lazy(async () => ({
  default: (await viewLoaders.credentials()).CredentialsCenter,
}));
const CommandPalette = lazy(async () => ({
  default: (await loadCommandPalette()).CommandPalette,
}));
const DetailInspector = lazy(async () => ({
  default: (await loadDetailInspector()).DetailInspector,
}));

function preloadView(view: View) {
  if (view === "agents") return;
  // Hover preloads are optional; navigation retains its normal loading path.
  void viewLoaders[view]().catch(() => undefined);
}

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
    capital,
    capitalError,
    events,
    preview,
    loading,
    error,
    connection,
    retryNow,
    controlRuntime,
    verifyCredentials,
    setProviderCredential,
    refreshCapital,
    setCapitalAuthorization,
    setExecutionMode,
    setBrokerCredential,
    brokerConnection,
    loadOlderEvents,
    loadingOlder,
    historyError,
    hasOlder,
  } = consoleState;
  const [view, setView] = useState<View>(storedView);
  const [selected, setSelected] = useState<SelectedEntity | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const selectionTrigger = useRef<HTMLElement | null>(null);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<
    string | null
  >(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(storedRail);
  const [actionError, setActionError] = useState<string | null>(null);
  const [, setClockTick] = useState(0);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [view]);

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

  useEffect(() => {
    const updateVisibleClock = () => {
      if (document.visibilityState === "visible") setClockTick(Date.now());
    };
    const timer = window.setInterval(updateVisibleClock, 30_000);
    document.addEventListener("visibilitychange", updateVisibleClock);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", updateVisibleClock);
    };
  }, []);

  const handleSelect = useCallback(
    (entity: SelectedEntity) => {
      if (
        document.activeElement instanceof HTMLElement &&
        !document.activeElement.closest(".inspector")
      ) {
        selectionTrigger.current = document.activeElement;
      }
      setSelected(entity);
      setInspectorOpen(true);
      setView((current) =>
        current === "credentials" || current === "capital" ? "field" : current,
      );
      const opportunityId = opportunityIdForEntity(status, entity);
      setSelectedOpportunityId(opportunityId);
    },
    [status],
  );

  const refreshedSelected = useMemo(
    () => refreshSelectedEntity(status, selected),
    [selected, status],
  );
  const localizedSelected = useMemo(
    () => relabelEntity(refreshedSelected, domain, t),
    [domain, refreshedSelected, t],
  );
  const selectionExpired = Boolean(
    selectedOpportunityId &&
      status &&
      !status.opportunities.some(
        (opportunity) => opportunity.id === selectedOpportunityId,
      ),
  );
  const effectiveOpportunityId = selectionExpired
    ? null
    : selectedOpportunityId;
  const defaultOpportunity = status ? latestRankLeader(status) : null;
  const defaultOpportunityEntity = defaultOpportunity
    ? {
        kind: "opportunity" as const,
        id: defaultOpportunity.id,
        label: defaultOpportunity.title,
        summary: defaultOpportunity as unknown as Record<string, unknown>,
      }
    : null;
  const inspectorSelected = localizedSelected ?? defaultOpportunityEntity;
  const fieldSelected = selectionExpired
    ? defaultOpportunityEntity
    : inspectorSelected;
  const visibleOperation = recentOperation(control?.operation);
  const runtimeReady = preview || Boolean(control?.runtime.ready);
  const schedule = runtimeSchedule(runtimeReady, Boolean(status), runtime);
  const showInspector =
    inspectorOpen && view !== "credentials" && view !== "capital";
  const currentCycleId =
    runtime?.config.autonomousStatus === "running"
      ? (runtime.config.currentCycleId ?? status?.currentPipelineId)
      : status?.currentPipelineId;

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
    return (
      <ConnectionScreen
        error={error}
        state={connection.status}
        onRetry={retryNow}
      />
    );
  if (!control && !preview)
    return <ConnectionScreen error={connection.message} onRetry={retryNow} />;

  return (
    <div
      className={cn(
        "app-shell",
        !showInspector && "inspector-closed",
        !railOpen && "rail-collapsed",
        view === "credentials" && "configuration-mode",
        view === "capital" && "capital-mode",
      )}
    >
      <a className="skip-link" href="#main-content">
        {t("skipToContent")}
      </a>
      <header className="topbar">
        <BrandLockup />
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
          {visibleOperation && (
            <span
              className={cn(
                "operation-progress",
                `is-${visibleOperation.status}`,
              )}
              role="status"
              aria-live="polite"
              title={visibleOperation.error}
            >
              {visibleOperation.status === "running" ? (
                <span className="loading-orbit" />
              ) : visibleOperation.status === "completed" ? (
                <CheckCircle2 />
              ) : (
                <TriangleAlert />
              )}
              {visibleOperation.status === "running"
                ? t("operationRunning", {
                    action: domain(visibleOperation.action),
                    phase: domain(visibleOperation.phase ?? t("working")),
                  })
                : visibleOperation.status === "completed"
                  ? t("operationComplete", {
                      action: domain(visibleOperation.action),
                    })
                  : t("operationFailed", {
                      action: domain(visibleOperation.action),
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
            onPointerEnter={() =>
              void loadCommandPalette().catch(() => undefined)
            }
            onFocus={() => void loadCommandPalette().catch(() => undefined)}
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
              type="button"
              className={cn("rail-item", view === id && "is-active")}
              key={id}
              aria-label={viewNavigationLabel(id, t)}
              title={viewNavigationLabel(id, t)}
              aria-current={view === id ? "page" : undefined}
              onPointerEnter={() => preloadView(id)}
              onFocus={() => preloadView(id)}
              onClick={() =>
                startTransition(() => {
                  setView(id);
                  setInspectorOpen(false);
                })
              }
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
            <span>
              {capital?.enabled ? t("capitalEnabled") : t("capitalDisabled")}
            </span>
          </div>
        </div>
      </nav>

      <main className="workspace" id="main-content" tabIndex={-1}>
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
            <p className="workspace-description">{t(`${view}Description`)}</p>
          </div>
          <div className="workspace-context">
            <span>
              {view === "capital"
                ? capital?.execution?.effective === "broker_paper"
                  ? t("tigerPaper")
                  : t("shadowSimulation")
                : domain(status?.environment ?? "shadow")}
            </span>
            <Separator orientation="vertical" />
            <span title={currentCycleId ?? undefined}>
              {schedule.key === "nextCycle"
                ? t(schedule.key, { time: relative(schedule.at) })
                : t(schedule.key)}
            </span>
          </div>
        </div>

        {view === "agents" && (
          <AgentModelSettings
            preview={preview}
            online={connection.status === "online"}
            runtimeActive={Boolean(
              control?.runtime.ready ||
                control?.runtime.host?.processAlive ||
                control?.runtime.supervisor?.childProcessAlive ||
                control?.operation?.status === "running",
            )}
            onSave={consoleState.updateAgentModels}
          />
        )}
        <Suspense fallback={<ViewLoading />}>
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
              onVerify={verifyCredentials}
              onSave={setProviderCredential}
              online={connection.status === "online"}
              onBrokerConnection={brokerConnection}
            />
          ) : view === "capital" ? (
            <CapitalConsole
              capital={capital}
              error={capitalError}
              control={control}
              preview={preview}
              online={connection.status === "online"}
              onRefresh={refreshCapital}
              onAuthorization={setCapitalAuthorization}
              onMode={setExecutionMode}
              onCredentials={setBrokerCredential}
              onBrokerConnection={brokerConnection}
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
                <>
                  <OperatingBrief
                    status={status}
                    runtime={runtime}
                    ready={runtimeReady}
                    stale={connection.stale}
                    preview={preview}
                    onNavigate={(nextView) =>
                      startTransition(() => {
                        setView(nextView);
                        setInspectorOpen(false);
                      })
                    }
                  />
                  <OpportunityField
                    status={status}
                    runtime={runtime}
                    selected={fieldSelected}
                    selectedOpportunityId={effectiveOpportunityId}
                    onSelect={handleSelect}
                  />
                </>
              )}
              {view === "ledger" && (
                <DecisionLedger
                  events={events}
                  status={status}
                  currentCycleId={currentCycleId}
                  selected={inspectorSelected}
                  onSelect={handleSelect}
                  onLoadOlder={loadOlderEvents}
                  loadingOlder={loadingOlder}
                  hasOlder={preview ? false : hasOlder}
                />
              )}
              {view === "overview" && (
                <SystemOverview
                  status={status}
                  runtime={runtime}
                  onSelect={handleSelect}
                />
              )}
              {view === "agents" && (
                <AgentDesk
                  status={status}
                  runtime={runtime}
                  events={events}
                  onSelect={handleSelect}
                />
              )}
              {view === "shadow" && (
                <ShadowBook
                  status={status}
                  runtime={runtime}
                  onSelect={handleSelect}
                />
              )}
              {view === "ledger" && (
                <EventTimeline events={events} onSelect={handleSelect} />
              )}
            </>
          )}
        </Suspense>
      </main>

      {showInspector && (
        <Suspense fallback={null}>
          <DetailInspector
            selected={inspectorSelected}
            status={status}
            preview={preview}
            selectionExpired={selectionExpired}
            liveFallbackAvailable={Boolean(defaultOpportunityEntity)}
            onClose={() => {
              setInspectorOpen(false);
              if (selectionTrigger.current?.isConnected)
                selectionTrigger.current.focus();
              else document.getElementById("main-content")?.focus();
            }}
          />
        </Suspense>
      )}

      {commandOpen && (
        <Suspense fallback={null}>
          <CommandPalette
            open={commandOpen}
            onOpenChange={setCommandOpen}
            status={status}
            events={events}
            onSelect={handleSelect}
          />
        </Suspense>
      )}
    </div>
  );
}

function ViewLoading() {
  return (
    <div className="view-loading" aria-hidden="true">
      <Skeleton />
      <Skeleton />
      <Skeleton />
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
      <BrandLockup />
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

function viewNavigationLabel(view: View, t: ReturnType<typeof useI18n>["t"]) {
  if (view === "field") return t("liveField");
  if (view === "ledger") return t("decisionLedger");
  if (view === "overview") return t("systemOverview");
  if (view === "agents") return t("agentDesk");
  if (view === "shadow") return t("shadowBook");
  if (view === "capital") return t("capitalDesk");
  return t("credentials");
}

function recentOperation(operation: ControlState["operation"] | undefined) {
  if (!operation || operation.status !== "completed") return operation ?? null;
  const completedAt = Date.parse(operation.completedAt ?? "");
  return Number.isFinite(completedAt) && Date.now() - completedAt < 15_000
    ? operation
    : null;
}

function viewHeading(view: View, t: ReturnType<typeof useI18n>["t"]) {
  if (view === "field") return t("firmInMotion");
  if (view === "ledger") return t("everyDecisionTrail");
  if (view === "overview") return t("operatingPosture");
  if (view === "agents") return t("specializedMinds");
  if (view === "shadow") return t("auditedShadowExpressions");
  if (view === "capital") return t("brokerCapital");
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
  if (
    entity.kind === "event" &&
    typeof summary.scoutId === "string" &&
    typeof summary.mode === "string"
  )
    return {
      ...entity,
      label: `${domain(summary.scoutId)} · ${domain(summary.mode)}`,
    };
  const eventType = summary.eventType;
  return typeof eventType === "string"
    ? { ...entity, label: domain(eventType) }
    : entity;
}
