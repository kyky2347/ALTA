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
    brokerEnvironment: "PAPER";
    dashboardBinding: string;
  };
};

export type CredentialSlot = {
  slot: string;
  label: string;
  category: "models" | "market_data" | "news" | "research";
  purpose: string;
  configured: boolean;
  operational: boolean;
  credentialRequirement: "required" | "optional";
  availableWithoutCredential?: boolean;
  source: string;
  sourceKind: "environment" | "external" | "missing";
  editable: boolean;
  fingerprint: string | null;
  verification: CredentialVerification;
};

export type CredentialVerificationStatus =
  | "healthy"
  | "auth_rejected"
  | "rate_limited"
  | "unavailable"
  | "unverified"
  | "not_required"
  | "not_configured";

export type CredentialVerification = {
  status: CredentialVerificationStatus;
  reason: string | null;
  checkedAt: string | null;
  latencyMs: number | null;
  httpStatus: number | null;
};

export type CredentialInventory = {
  revision: string;
  configuredSlots: string[];
  verification: {
    checkedAt: string | null;
    expiresAt: string | null;
    stale: boolean;
  };
  slots: CredentialSlot[];
  providerNetwork: Array<{
    category: string;
    providers: string[];
  }>;
  trading: {
    provider: "Tiger Trade";
    mode: "paper_only";
    configured: boolean;
    editable: false;
    source: string;
    sourceKind: "environment" | "external" | "missing";
    fingerprint: string | null;
    authorizationEnabled?: boolean;
    authorizationPosture?: string;
    status:
      | "configured_external_capital_disabled"
      | "not_configured_capital_disabled"
      | "invalid_external_config";
  };
};

export type PaperCapitalPosition = {
  symbol: string;
  securityType: string;
  currency: string;
  quantity: string | null;
  averageCost: string | null;
  marketPrice: string | null;
  marketValue: string | null;
  unrealizedPnl: string | null;
  unrealizedPnlPercent: string | null;
  realizedPnl: string | null;
  todayPnl: string | null;
  salableQuantity: string | null;
};

export type PaperCapitalOrder = {
  reference: string;
  symbol: string;
  securityType: string;
  side: string;
  orderType: string;
  status: string;
  quantity: string | null;
  filled: string | null;
  remaining: string | null;
  limitPrice: string | null;
  averageFillPrice: string | null;
  commission: string | null;
  realizedPnl: string | null;
  timeInForce: string;
  outsideRegularHours: boolean;
  createdAt: string | null;
  updatedAt: string | null;
  filledAt: string | null;
};

export type PaperCapitalSnapshot = {
  paper: true;
  accountBinding: true;
  accountFingerprint: string;
  observedAt: string;
  brokerUpdatedAt: string | null;
  savedAt: string;
  positionCount: number;
  openOrderCount: number;
  recentOrderCount: number;
  mutationPolicy: "risk_budgeted_limit_day_v1";
  maxOrderNotional: string | null;
  assets: {
    currency?: string;
    cashBalance?: string | null;
    cashAvailableForTrade?: string | null;
    netLiquidation?: string | null;
    grossPositionValue?: string | null;
    buyingPower?: string | null;
    unrealizedPnl?: string | null;
    realizedPnl?: string | null;
    maintenanceMargin?: string | null;
  };
  positions: PaperCapitalPosition[];
  orders: PaperCapitalOrder[];
};

export type PaperCapitalAuditEvent = {
  id: string;
  action: string;
  result: "succeeded" | "failed";
  knownAt: string;
  accountFingerprint: string | null;
  errorFingerprint?: string;
};

export type PaperCapitalStatus = {
  version: 1;
  provider: "Tiger Trade";
  environment: "PAPER";
  configured: boolean;
  requestedEnabled: boolean;
  enabled: boolean;
  authorizationGeneration: number | null;
  closeOnly: boolean;
  drainRequired: boolean;
  posture:
    | "disabled"
    | "not_configured"
    | "authorization_invalid"
    | "snapshot_invalid"
    | "configuration_changed"
    | "paper_enabled"
    | "paper_recovery_required"
    | "paper_ready_disabled";
  accountFingerprint: string | null;
  configurationFingerprint: string | null;
  mutationPolicy: "risk_budgeted_limit_day_v1";
  riskPolicy: {
    maxOrderNotional: string;
    maxOpenPositions: string;
    maxDispatchQuoteAgeSeconds: string;
  };
  instrumentPolicy: "us_stock_only";
  outsideRegularHours: false;
  requiresStoppedRuntime: true;
  lastChangedAt: string | null;
  lastPreflightAt: string | null;
  configurationError: string | null;
  authorizationError: string | null;
  snapshotError: string | null;
  snapshot: PaperCapitalSnapshot | null;
  audit: PaperCapitalAuditEvent[];
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
    rankingRunId: string;
    rankingRunItemCount: number;
    rankingRunComplete: boolean;
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
  researchTrials?: number;
  selectionPolicyVersion?: string;
  selectionCriticalZ?: string | null;
  selectionAdjustedConfidence95LowerBps?: string | null;
  selectionAdjustedLowerBoundAboveZero?: boolean;
};

export type AlphaCapitalGovernanceSummary = {
  posture?: string;
  capitalMultiplier?: string;
  sampleSize?: number;
  windowSize?: number;
  recentMeanAlphaBps?: string | null;
  confidence95LowerAlphaBps?: string | null;
  confidence95UpperAlphaBps?: string | null;
  researchTrials?: number;
  selectionAdjustedLowerAlphaBps?: string | null;
  selectionCriticalZ?: string | null;
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

export type ExecutionQualitySummary = {
  posture?: string;
  measuredPositions?: number;
  minimumSample?: number;
  meanEstimatedCostBps?: string | null;
  meanRealizedCostBps?: string | null;
  meanCostSurpriseBps?: string | null;
  withinBudgetRate?: string | null;
  openFillRate?: string | null;
  openFills?: number;
  openNoFills?: number;
  exitFills?: number;
  exitNoFills?: number;
  warning?: string;
};

export type ExecutionCostGovernanceSummary = {
  policyVersion?: string;
  sourcePortfolioPolicyVersion?: string;
  expressionKind?: string;
  posture?: string;
  sampleSize?: number;
  windowSize?: number;
  minimumSample?: number;
  meanEstimatedCostBps?: string | null;
  meanRealizedCostBps?: string | null;
  meanCostSurpriseBps?: string | null;
  meanAbsoluteSurpriseBps?: string | null;
  withinBudgetRate?: string | null;
  alphaReserveBps?: string;
  observedThrough?: string | null;
  reasonCodes?: string[];
};

export type PortfolioRiskSummary = {
  policyVersion?: string;
  posture?: string;
  knownOpenPositions?: number;
  referenceNav?: string;
  grossNotional?: string;
  grossNavBps?: string;
  grossLimitNavBps?: string;
  aggregateStressLoss?: string;
  stressNavBps?: string;
  stressLimitNavBps?: string;
  underlyingLimitNavBps?: string;
  alphaSourceLimitNavBps?: string;
  catalystLimitNavBps?: string;
  systematicExposureLimitNavBps?: string;
  mostConstrainedBucket?: {
    kind: string;
    key: string;
    grossNavBps: string;
    limitNavBps: string;
    utilization: string;
  } | null;
  underlyingBuckets?: Array<{
    underlyingKey: string;
    openPositions: number;
    grossNotional: string;
    grossNavBps: string;
    estimatedStressLoss: string;
  }>;
  alphaSourceBuckets?: Array<{
    alphaSource: string;
    openPositions: number;
    grossNotional: string;
    grossNavBps: string;
    estimatedStressLoss: string;
  }>;
  catalystBuckets?: Array<{
    catalystKey: string;
    openPositions: number;
    grossNotional: string;
    grossNavBps: string;
    estimatedStressLoss: string;
  }>;
  systematicExposureBuckets?: Array<{
    tag: string;
    grossNotional: string;
    grossNavBps: string;
  }>;
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
  executionQuality?: ExecutionQualitySummary;
  executionCostGovernance?: Partial<
    Record<"stock" | "etf" | "option", ExecutionCostGovernanceSummary>
  >;
  portfolioRisk?: PortfolioRiskSummary | null;
  warning?: string;
};

export type ResearchAttentionSummary = {
  version: string;
  knownAt: string;
  observedThrough?: string | null;
  maximumWindow: number;
  minimumSample: number;
  concentrationThreshold: string;
  sampleSize: number;
  uniqueEntities: number;
  topEntity?: string | null;
  topEntityShare?: string | null;
  concentrationHhi?: string | null;
  effectiveBreadth?: string | null;
  uniqueArchetypes?: number;
  archetypeEffectiveBreadth?: string | null;
  horizonMix?: Record<string, number>;
  directionMix?: Record<string, number>;
  posture: "insufficient_sample" | "balanced" | "concentrated";
  continuationScoutId?: string | null;
  assignments: Array<{
    scoutId: string;
    mode: "unconstrained" | "continue_lead" | "expand_coverage";
    deprioritizedEntities: string[];
    targetArchetype?: string | null;
    targetHorizonBucket?: "short" | "medium" | "long" | null;
    directive: string;
  }>;
  warning: string;
};

export type OpportunityContinuitySummary = {
  version: string;
  knownAt: string;
  scanLimit: number;
  frozenLimit: number;
  registryActive: number;
  scannedActive: number;
  frozenActive: number;
  pendingQuestions: number;
  deferredQuestions: number;
  nextResearchDueAt?: string | null;
  expiringActive: number;
  staleActive: number;
  oldestActiveDays: number;
  earliestDecisionDeadlineAt?: string | null;
  selectedOpportunityIds: string[];
  priorityOpportunityIds: string[];
  selectionTruncated: boolean;
  registryScanSaturated: boolean;
  posture: "empty" | "healthy" | "backlog" | "expiring" | "stale";
  warning: string;
};

export type ResearchOperationsSummary = {
  version: string;
  posture: "waiting" | "active" | "degraded" | "cross_checked";
  windowRuns: number;
  candidateRuns: number;
  noOpRuns: number;
  failedRuns: number;
  completedToolCalls: number;
  failedToolCalls: number;
  uniqueSourceDomains: number;
  independentEvidenceOrigins: number;
  citedSources: number;
  sourceRoleCollisions: number;
  sourceFamilies: string[];
  crossCheckedRuns: number;
  screenGradeRuns: number;
  retriedRuns: number;
  retryRecoveredRuns: number;
  contractRejectedRuns: number;
  deadlineFailedRuns: number;
  followUpAssignedRuns: number;
  followUpExecutedRuns: number;
  followUpNoOpRuns: number;
  totalTokens: number;
  averageLatencyMs?: number | null;
  minds: Array<{
    scoutId: string;
    posture:
      | "waiting"
      | "active"
      | "degraded"
      | "cross_checked"
      | "screen_grade";
    lastRunAt?: string | null;
    latestStatus?: string | null;
    latestErrorCode?: string | null;
    windowRuns: number;
    candidateRuns: number;
    noOpRuns: number;
    failedRuns: number;
    completedToolCalls: number;
    failedToolCalls: number;
    uniqueSourceDomains: number;
    independentEvidenceOrigins: number;
    citedSources: number;
    sourceRoleCollisions: number;
    sourceFamilies: string[];
    evidenceRoles: string[];
    crossCheckedRuns: number;
    screenGradeRuns: number;
    retriedRuns: number;
    retryRecoveredRuns: number;
    contractRejectedRuns: number;
    deadlineFailedRuns: number;
    followUpAssignedRuns: number;
    followUpExecutedRuns: number;
    followUpNoOpRuns: number;
    latestAttemptCount: number;
    totalTokens: number;
    averageLatencyMs?: number | null;
  }>;
  disclosure: string;
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
  researchAttention?: ResearchAttentionSummary | null;
  opportunityContinuity?: OpportunityContinuitySummary | null;
  researchOperations?: ResearchOperationsSummary | null;
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
  snapshotOnly?: boolean;
};
