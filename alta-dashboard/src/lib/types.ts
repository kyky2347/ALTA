export type ConsoleOperation = {
  id: string;
  action: "start" | "stop" | "restart";
  status: "running" | "completed" | "failed";
  startedAt: string;
  completedAt?: string;
  error?: string;
  phase?: string;
};

export type ConsoleConnection = {
  status:
    | "connecting"
    | "online"
    | "degraded"
    | "offline"
    | "unauthorized"
    | "incompatible";
  message: string | null;
  lastSuccessfulAt: string | null;
  consecutiveFailures: number;
  retryAt: string | null;
  stale: boolean;
};

export type ControlState = {
  console: {
    protocolVersion: number;
    instanceId: string;
    startedAt: string;
    uptimeSeconds: number;
  };
  runtime: {
    installed: boolean;
    ready: boolean;
    platformActive: boolean;
    endpoint: string;
    capitalMode: string;
    host?: {
      state?: string;
      processId?: number;
      processAlive?: boolean;
    } | null;
    supervisor?: {
      state?: string;
      childPid?: number;
      childProcessAlive?: boolean;
    } | null;
  };
  environment: {
    docker?: { ready?: boolean; version?: string; error?: string };
    services?: { configured?: boolean; states?: Record<string, string> };
    error?: string;
  };
  operation: ConsoleOperation | null;
  safety: {
    environment: string;
    capitalMode: string;
    dashboardBinding: string;
  };
};

export type CredentialSlot = {
  slot: string;
  label: string;
  category: "models" | "market_data" | "news" | "research";
  purpose: string;
  configured: boolean;
  source: string;
  sourceKind: "environment" | "external" | "missing";
  editable: boolean;
  fingerprint: string | null;
};

export type CredentialInventory = {
  revision: string;
  configuredSlots: string[];
  slots: CredentialSlot[];
  trading: {
    provider: "Tiger Trade";
    mode: "paper_only";
    configured: false;
    editable: false;
    status: "capital_runtime_disabled";
  };
};

export type AgentRun = {
  id: string;
  runId: string;
  cycleId?: string;
  status: string;
  errorCode?: string | null;
  knownAt: string;
  modelProvider?: string;
  modelId?: string;
  usage?: Record<string, number>;
  latencyMs?: number;
  threadId?: string;
};

export type Opportunity = {
  id: string;
  title: string;
  status: string;
  knownAt: string;
  foundryState?: string;
};

export type Assessment = {
  id: string;
  opportunityId: string;
  assessor: string;
  verdict: string;
  score: string | number;
  recommendation?: string;
  confidence?: string | number;
  knownAt: string;
  underwriting?: Record<string, unknown>;
};

export type AltaEvent = {
  cursor: number;
  eventId: string;
  eventType: string;
  aggregateType: string;
  aggregateId: string;
  environment: string;
  knownAt: string;
  payload: Record<string, unknown>;
};

export type MvpStatus = {
  status: string;
  environment: string;
  currentPipelineId?: string | null;
  eventCursor: number;
  sources: Array<Record<string, unknown> & { id: string; knownAt: string }>;
  pipeline: Array<{
    id: string;
    knownAt: string;
    eventType: string;
    detail: Record<string, unknown>;
  }>;
  runs: Array<Omit<AgentRun, "runId"> & { role: string }>;
  agents: AgentRun[];
  candidates: Array<{
    id: string;
    title: string;
    knownAt: string;
    alphaArchetype?: string;
  }>;
  opportunities: Opportunity[];
  ranks: Array<{
    id: string;
    opportunityId: string;
    book: string;
    position: number;
    score: string | number;
    knownAt: string;
  }>;
  expressions: Array<{
    id: string;
    opportunityId: string;
    kind: string;
    status: string;
    knownAt: string;
  }>;
  shadowPositions: Array<{
    id: string;
    expressionId: string;
    symbol: string;
    status: string;
    quantity?: string | number;
    knownAt: string;
    openedAt?: string;
    closedAt?: string;
  }>;
  assessments: Assessment[];
  discussions: Array<{
    id: string;
    opportunityId: string;
    eventType: string;
    knownAt: string;
    detail: Record<string, unknown>;
  }>;
};

export type AlphaEvidenceSummary = {
  posture?: string;
  sampleSize?: number;
  minimumSample?: number;
  meanAlphaBps?: string | null;
  confidence95LowerBps?: string | null;
  confidence95UpperBps?: string | null;
};

export type AlphaCapitalGovernanceSummary = {
  posture?: string;
  capitalMultiplier?: string;
  sampleSize?: number;
  windowSize?: number;
  recentMeanAlphaBps?: string | null;
  maxDrawdownNavBps?: string;
  evidencePosture?: string;
};

export type UnderwritingCalibrationSummary = {
  posture?: string;
  sampleSize?: number;
  minimumSample?: number;
  meanForecastErrorBps?: string | null;
  meanAbsoluteErrorBps?: string | null;
  directionalHitRate?: string | null;
};

export type ForecastCalibrationGovernanceSummary = {
  posture?: string;
  expressionKind?: string;
  capitalMultiplier?: string;
  sampleSize?: number;
  windowSize?: number;
  minimumSample?: number;
  meanForecastErrorBps?: string | null;
  meanAbsoluteErrorBps?: string | null;
  directionalHitRate?: string | null;
  alphaReserveBps?: string;
};

export type PathDiagnosticsSummary = {
  posture?: string;
  measuredPositions?: number;
  minimumSample?: number;
  meanMaximumFavorableExcursionBps?: string | null;
  meanMaximumAdverseExcursionBps?: string | null;
  meanMaximumDrawdownBps?: string | null;
  meanExitCaptureRatio?: string | null;
  positiveExcursionMissRate?: string | null;
  warning?: string;
};

export type AlphaSummary = {
  measurement?: string;
  closedPositions?: number;
  openPositions?: number;
  positiveReturnRate?: string | null;
  meanNetReturnBps?: string | null;
  meanRealizedAlphaBps?: string | null;
  cumulativeNetPnl?: string;
  lastMeasuredAt?: string | null;
  alphaEvidence?: AlphaEvidenceSummary;
  capitalGovernance?: AlphaCapitalGovernanceSummary;
  underwritingCalibration?: UnderwritingCalibrationSummary;
  forecastCalibrationGovernance?: ForecastCalibrationGovernanceSummary;
  pathDiagnostics?: PathDiagnosticsSummary;
  warning?: string;
};

export type RuntimeDetail = {
  minds: Array<{
    id: string;
    knownAt: string;
    turnCount: number;
    contextTokens: number;
    rollingSummary?: string;
    modelProvider?: string;
    modelId?: string;
  }>;
  sourceCursors: Array<{ source: string; cursor: string; knownAt: string }>;
  alpha?: AlphaSummary;
  config: Record<string, unknown> & {
    autonomousStatus?: string;
    currentCycleId?: string;
    lastHeartbeatAt?: string;
    lastCycleResult?: string;
    nextCycleAt?: string;
    consecutiveFailures?: number;
    capitalMode?: string;
  };
};

export type SelectedEntity = {
  kind: "opportunity" | "run" | "expression" | "event" | "position";
  id: string;
  label: string;
  summary?: Record<string, unknown>;
};
