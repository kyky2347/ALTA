import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "en" | "zh-CN";

const STORAGE_KEY = "alta.console.locale";

const en = {
  productSubtitle: "Autonomous LLM Trading Asterism",
  switchToChinese: "Switch to Chinese",
  switchToEnglish: "Switch to English",
  language: "Language",
  close: "Close",
  commandPalette: "Command palette",
  searchCommand: "Search for a command to run…",
  suggestions: "Suggestions",
  syntheticPreview: "Synthetic preview",
  heartbeat: "Heartbeat {{time}}",
  findAnything: "Find anything",
  dashboardSections: "Dashboard sections",
  toggleNavigation: "Toggle navigation rail",
  liveField: "Live field",
  decisionLedger: "Decision ledger",
  systemOverview: "System overview",
  agentDesk: "Agent desk",
  shadowBook: "Shadow book",
  researchOnly: "Research only",
  shadowEnvironment: "Shadow environment",
  capitalDisabled: "Capital disabled",
  lifecycleRejected: "Lifecycle action was not accepted",
  dismiss: "Dismiss",
  olderHistoryUnavailable: "Older history is temporarily unavailable",
  liveSyncContinues: "Live synchronization continues independently.",
  firmInMotion: "The firm, in motion",
  everyDecisionTrail: "Every decision leaves a trail",
  operatingPosture: "Operating posture",
  specializedMinds: "Specialized minds",
  auditedShadowExpressions: "Audited shadow expressions",
  noActiveCycle: "No active cycle",
  nextCycle: "Next cycle {{time}}",
  scheduleUnavailable: "Schedule unavailable",
  findAnyRecord: "Find any ALTA record",
  searchRecords: "Search opportunities, agents, expressions, positions…",
  noMatchingRecord: "No matching durable record.",
  records: "Records",
  openingConsole: "Opening the operator console",
  openingConsoleDetail:
    "Establishing a local, authenticated view of the research runtime.",
  secureLaunchRequired: "This console needs its secure launch URL",
  dashboardUpdateRequired: "Dashboard update required",
  reconnectingLocalService: "Reconnecting to the local operator service",
  secureLaunchHelp:
    "Run ./alta dashboard and open the one-time local URL printed in the terminal.",
  automaticRecovery:
    "The page will recover automatically when the local service is available.",
  retryNow: "Retry now",
  runtimeStoppedSnapshot: "Runtime stopped · saved browser snapshot",
  reconnecting: "Reconnecting",
  liveSyncDegraded: "Live synchronization is degraded",
  restoringConnection: "ALTA is restoring the live connection.",
  lastSynchronized: "Last synchronized {{time}}.",
  retry: "Retry",
  runtimeRecoveringTitle: "The research runtime is recovering.",
  operatorShellReady: "The operator shell is ready.",
  runtimeRecoveringDetail:
    "ALTA is bootstrapping dependencies or restoring readiness. Controls remain locked until this transition settles.",
  runtimeInstalledDetail:
    "Start the installed service to resume autonomous discovery, committee review, audited expression, and shadow observation.",
  runtimeInstallDetail:
    "Start from this console. ALTA will prepare locked dependencies, install its local user service, and wait for readiness automatically.",
  restoringReadiness: "Restoring readiness…",
  startResearchRuntime: "Start research runtime",
  noRollingSummary:
    "No durable rolling summary is available for this agent role.",
  model: "Model",
  turns: "Turns",
  context: "Context",
  shadowPosition: "{{symbol}} shadow position",
  assessmentLabel: "{{assessor}} assessment · {{verdict}}",
  controlFailed: "Control action failed",
  runtimeReady: "runtime ready",
  runtimeRecovering: "runtime recovering",
  runtimeStopped: "runtime stopped",
  consoleReconnecting: "console reconnecting",
  operationRunning: "{{action}} · {{phase}}",
  operationComplete: "{{action}} complete",
  operationFailed: "{{action}} failed · retry from controls",
  working: "working",
  chronologicalLedger: "Chronological decision ledger",
  loadedEvents: "{{count}} loaded events",
  appendOnly: "append only",
  ledgerFilterPlaceholder: "Filter by event, role, cycle, opportunity, status…",
  filterLoadedEvents: "Filter loaded decision events",
  filterEventFamily: "Filter by event family",
  allEventFamilies: "All event families",
  filterDecisionScope: "Filter by current decision scope",
  allLoadedScopes: "All loaded scopes",
  currentCycle: "Current cycle",
  leadingOpportunity: "Leading opportunity",
  loading: "Loading…",
  loadOlder: "Load 100 older",
  historyStartReached: "History start reached",
  noMatchingEvents: "No matching events",
  noRecordedEvents: "No recorded events yet",
  broadenFilters: "Clear or broaden the loaded-history filters.",
  ledgerWillFill:
    "The ledger will fill as the autonomous pipeline emits durable events.",
  recordedWithoutSummary: "Recorded without public summary",
  selectedRecordInspector: "Selected record inspector",
  recordLabel: "{{kind}} record",
  inspector: "Inspector",
  selectAnyRecord: "Select any record",
  selectAnyRecordDetail:
    "Open an opportunity, agent run, committee event, expression, or shadow position to inspect its durable record.",
  savedSystemRecord: "Saved system record · not private chain-of-thought",
  brief: "Brief",
  evidence: "Evidence",
  record: "Record",
  normalizedJson: "Normalized JSON",
  researchBoundary: "Research-only · shadow environment · capital disabled",
  decisionPacket: "Decision packet",
  noPublicBrief: "No public brief has been saved for this record.",
  independentAssessments: "Independent assessments",
  noRecommendation: "No recommendation summary",
  scoreConfidence: "Score {{score}} · confidence {{confidence}}",
  committeeExchange: "Committee exchange",
  provenance: "Provenance",
  evidenceReferences: "Evidence references",
  noneSaved: "None saved",
  artifacts: "Artifacts",
  committeeRecords: "Committee records",
  artifactNumber: "Artifact {{number}}",
  hash: "Hash {{hash}}…",
  hashUnavailable: "Hash unavailable",
  noArtifact:
    "No run artifact is attached to this selected record. Opportunity evidence may be represented through assessments and committee events.",
  noPublicSummary: "No public summary",
  loadingDurableRecord: "Loading the durable record…",
  originalArtifact: "Original saved artifact",
  recentEventReplay: "Recent event replay",
  replayRibbon: "Replay ribbon",
  loadedDurableEvents: "{{count}} loaded durable events",
  waitingForEvents: "Waiting for events",
  noReplayRange: "No replay range",
  replayLoadedHistory: "Replay loaded decision history",
  live: "LIVE",
  replayMode: "REPLAY",
  waitingFirstEvent: "Waiting for the first event",
  pauseReplay: "Pause replay",
  playReplay: "Play replay",
  playLoadedHistory: "Play loaded history",
  liveNow: "Live now",
  liveOpportunityFlow: "Live opportunity flow",
  opportunityFlowStage: "Opportunity flow stage",
  discovery: "Discovery",
  foundry: "Foundry",
  committee: "Committee",
  audit: "Audit",
  unclassified: "Unclassified",
  noCandidates: "No candidates yet",
  building: "Building",
  foundryWaiting: "Foundry is waiting for candidates",
  modelPending: "Model pending",
  assessments: "Assessments",
  arguments: "Arguments",
  expressionAudit: "Expression & audit",
  selectedCarrier: "Selected carrier",
  noExpression: "No expression selected",
  auditBoundary: "Audit boundary",
  waiting: "Waiting",
  shadowObservation: "Shadow observation",
  noPosition: "No position",
  activeRecentlyUpdated: "Active or recently updated",
  waitingHistorical: "Waiting or historical",
  savedArtifactsTruth:
    "Private chain-of-thought is not exposed; saved artifacts and handoffs are.",
  handoffLabel: "Handoff from {{source}} to {{target}}{{time}}",
  start: "Start",
  stop: "Stop",
  restart: "Restart",
  runtimeControls: "Research runtime controls",
  startRuntimeAria: "Start research runtime",
  startRuntimeTip: "Prepare and start the shadow-research service",
  restartRuntimeAria: "Restart research runtime",
  restartRuntimeTip: "Restart the research service",
  stopRuntimeAria: "Stop research runtime",
  stopRuntimeConfirm: "Stop the research runtime?",
  restartRuntimeConfirm: "Restart the research runtime?",
  stopRuntimeDetail:
    "ALTA will stop its agent service, supervisor, PostgreSQL, and Redis. The local dashboard shell remains available so you can start it again.",
  restartRuntimeDetail:
    "The autonomous service will restart and wait for readiness. No capital or broker path is available from this console.",
  cancel: "Cancel",
  stopSafely: "Stop safely",
  observationNotBrokerage: "Observation, not brokerage",
  observationNotBrokerageDetail:
    "Every row is a research shadow position. This dashboard exposes no capital or live-order path.",
  forwardAlphaEvidence: "Forward Alpha evidence",
  forwardAlphaDetail:
    "Cost-adjusted Shadow outcomes relative to SPY, measured from entry-frozen decisions. This is an evidence ledger, not a performance claim.",
  comparableCloses: "Comparable closes",
  minimum: "{{count}} minimum",
  moreBeforeCalibration:
    "{{count}} more before calibration can affect forecasts.",
  calibrationReached:
    "Minimum calibration sample reached; rolling evidence now governs forecasts.",
  meanRealizedAlpha: "Mean realized Alpha",
  forecastMae: "Forecast MAE",
  forecastMaeDetail: "Absolute error on comparable direct-stock forecasts.",
  directionalHitRate: "Directional hit rate",
  directionalHitDetail:
    "Descriptive only; zero forecasts and outcomes are excluded.",
  forecastReserve: "Forecast reserve",
  forecastReserveInactive: "Inactive while the sample is immature.",
  forecastReserveActive: "Deducted from new expected Alpha before costs.",
  capitalPosture: "Capital posture",
  capitalPostureDetail:
    "The tightest forward-evidence multiplier; it can never add leverage.",
  observedLifecycleQuality: "Observed lifecycle quality",
  observedLifecycleDetail:
    "Executable exit observations separate opportunity quality from path risk and exit capture. They never create an automatic exit.",
  measured: "{{count}} measured",
  meanFavorableExcursion: "Mean favorable excursion",
  meanAdverseExcursion: "Mean adverse excursion",
  meanExitCapture: "Mean exit capture",
  positivePathMissed: "Positive path missed",
  noClosedSample: "No closed, benchmarked Shadow sample is available yet.",
  lastMeasured: "Last measured {{time}}",
  instrument: "Instrument",
  status: "Status",
  quantity: "Quantity",
  opened: "Opened",
  expression: "Expression",
  noShadowPositions: "No shadow positions are open or recently closed.",
  awaitingIndependentCloses: "Awaiting enough independent closes",
  candidates: "Candidates",
  recentFoundryInputs: "Recent foundry inputs",
  opportunities: "Opportunities",
  deduplicatedTheses: "Deduplicated theses",
  agentRoles: "Agent roles",
  persistentMinds: "{{count}} persistent minds",
  expressions: "Expressions",
  auditedCarriers: "Audited carriers",
  shadowPositions: "Shadow positions",
  eventCursor: "Event cursor",
  appendOnlyLedger: "Append-only ledger",
  sourcePosture: "Source posture",
  observed: "observed",
  noSourcePosture: "No source posture has been recorded.",
  traderMinds: "Trader minds",
  minds: "{{count}} minds",
  noRollingSummarySaved: "No rolling summary saved",
  dashboardRenderFailed: "The dashboard view could not be rendered",
  dashboardRenderFailedDetail:
    "The research runtime was not changed. Reload the local console to rebuild this browser view from durable backend state.",
  reloadConsole: "Reload console",
  credentials: "Credentials",
  secureProviderConfiguration: "Secure provider configuration",
  secureConfiguration: "Secure configuration",
  providerCredentials: "Provider credentials",
  credentialCenterDetail:
    "Configure model, market-data, news, and research providers without opening backend files.",
  credentialSummary: "Credential summary",
  configured: "Configured",
  supported: "Supported",
  refresh: "Refresh",
  credentialChangesLocked: "Credential changes are locked while ALTA runs",
  stopBeforeCredentialChange:
    "Stop the research runtime before replacing a credential. This prevents mixed provider state inside an active cycle.",
  credentialCenterUnavailable: "Credential center needs attention",
  credentialRefreshFailed: "The credential inventory could not be refreshed.",
  credentialSaveFailed: "The credential was not saved.",
  credentialStored: "Credential stored",
  credentialMissing: "Credential required",
  trading: "Trading",
  paperExecutionDisabled: "Paper execution disabled",
  notConfigured: "Not configured",
  source: "Source",
  safeFingerprint: "Safe fingerprint",
  activation: "Activation",
  nextRuntimeStart: "Next runtime start",
  notActive: "Not active",
  newProviderToken: "New provider token",
  pasteTokenPlaceholder: "Paste a new token — it will not be shown again",
  environmentCredentialLocked:
    "This value comes from an environment variable. Unset it before replacing the external credential.",
  writeOnlyCredentialHelp:
    "Write-only: ALTA validates and stores this outside the repository with owner-only permissions.",
  secretNeverReturned: "Secret is never returned to the browser",
  savingSecurely: "Saving securely…",
  saveAndActivate: "Save for next start",
  credentialSaved: "Credential saved.",
  credentialSavedDetail:
    "The input was cleared and the new fingerprint is now visible.",
  selectProvider: "Select a provider to inspect its safe configuration state.",
  paperBoundaryTitle: "Trading remains behind a separate Paper-only boundary",
  paperBoundaryDetail:
    "This research build does not accept broker credentials or expose live-order controls. Tiger Trade is shown so the boundary is explicit, not hidden.",
  purposeDeepseek: "Primary agent inference and research",
  purposeXai: "Independent debate and web-aware research",
  purposeKimi: "Independent analysis and long-context research",
  purposeMassive: "US equity and option market data",
  purposeFinlight: "Normalized market news",
  purposeBrave: "Open-web search",
  purposeJina: "Readable web content extraction",
  purposeOpenalex: "Academic and research discovery",
  yes: "Yes",
  no: "No",
  unavailable: "—",
} as const;

type MessageKey = keyof typeof en;

const zhCN: Record<MessageKey, string> = {
  productSubtitle: "自主 LLM 交易星群",
  switchToChinese: "切换为中文",
  switchToEnglish: "Switch to English",
  language: "语言",
  close: "关闭",
  commandPalette: "命令面板",
  searchCommand: "搜索要运行的命令…",
  suggestions: "搜索建议",
  syntheticPreview: "合成数据预览",
  heartbeat: "心跳 {{time}}",
  findAnything: "全局查找",
  dashboardSections: "控制台分区",
  toggleNavigation: "展开或收起导航栏",
  liveField: "实时机会场",
  decisionLedger: "决策账本",
  systemOverview: "系统总览",
  agentDesk: "Agent 工作台",
  shadowBook: "影子账簿",
  researchOnly: "仅限研究",
  shadowEnvironment: "影子环境",
  capitalDisabled: "资金已禁用",
  lifecycleRejected: "生命周期操作未被接受",
  dismiss: "关闭",
  olderHistoryUnavailable: "暂时无法读取更早历史",
  liveSyncContinues: "实时同步仍会独立继续。",
  firmInMotion: "正在运转的虚拟交易公司",
  everyDecisionTrail: "每个决策都有可追溯记录",
  operatingPosture: "当前运行态势",
  specializedMinds: "专业化 Agent 思维网络",
  auditedShadowExpressions: "经审计的影子表达",
  noActiveCycle: "当前没有活动周期",
  nextCycle: "下个周期 {{time}}",
  scheduleUnavailable: "调度信息不可用",
  findAnyRecord: "查找任意 ALTA 记录",
  searchRecords: "搜索机会、Agent、表达或持仓…",
  noMatchingRecord: "没有匹配的持久化记录。",
  records: "记录",
  openingConsole: "正在打开操作控制台",
  openingConsoleDetail: "正在建立本机、已鉴权的研究运行时视图。",
  secureLaunchRequired: "此控制台需要安全启动链接",
  dashboardUpdateRequired: "需要更新控制台",
  reconnectingLocalService: "正在重新连接本机操作服务",
  secureLaunchHelp:
    "请运行 ./alta dashboard，并打开终端中输出的一次性本机链接。",
  automaticRecovery: "本机服务恢复后，此页面会自动重新连接。",
  retryNow: "立即重试",
  runtimeStoppedSnapshot: "运行时已停止 · 显示已保存的浏览器快照",
  reconnecting: "正在重新连接",
  liveSyncDegraded: "实时同步已降级",
  restoringConnection: "ALTA 正在恢复实时连接。",
  lastSynchronized: "上次同步于 {{time}}。",
  retry: "重试",
  runtimeRecoveringTitle: "研究运行时正在恢复。",
  operatorShellReady: "操作控制台已就绪。",
  runtimeRecoveringDetail:
    "ALTA 正在启动依赖或恢复就绪状态；过渡完成前控制功能保持锁定。",
  runtimeInstalledDetail:
    "启动已安装的服务，以恢复自主发现、委员会评审、审计表达和影子观察。",
  runtimeInstallDetail:
    "直接从此控制台启动。ALTA 会自动准备锁定依赖、安装本机用户服务并等待系统就绪。",
  restoringReadiness: "正在恢复就绪状态…",
  startResearchRuntime: "启动研究运行时",
  noRollingSummary: "该 Agent 角色暂无持久化滚动摘要。",
  model: "模型",
  turns: "轮次",
  context: "上下文",
  shadowPosition: "{{symbol}} 影子持仓",
  assessmentLabel: "{{assessor}} 评估 · {{verdict}}",
  controlFailed: "控制操作失败",
  runtimeReady: "运行时就绪",
  runtimeRecovering: "运行时恢复中",
  runtimeStopped: "运行时已停止",
  consoleReconnecting: "控制台重连中",
  operationRunning: "{{action}} · {{phase}}",
  operationComplete: "{{action}} · 已完成",
  operationFailed: "{{action}} · 失败，请从控制区重试",
  working: "处理中",
  chronologicalLedger: "按时间排序的决策账本",
  loadedEvents: "已载入 {{count}} 条事件",
  appendOnly: "仅追加",
  ledgerFilterPlaceholder: "按事件、角色、周期、机会或状态筛选…",
  filterLoadedEvents: "筛选已载入的决策事件",
  filterEventFamily: "按事件类别筛选",
  allEventFamilies: "全部事件类别",
  filterDecisionScope: "按当前决策范围筛选",
  allLoadedScopes: "全部已载入范围",
  currentCycle: "当前周期",
  leadingOpportunity: "首要机会",
  loading: "正在载入…",
  loadOlder: "载入更早 100 条",
  historyStartReached: "已到达历史起点",
  noMatchingEvents: "没有匹配事件",
  noRecordedEvents: "尚无已记录事件",
  broadenFilters: "请清除筛选条件或扩大筛选范围。",
  ledgerWillFill: "自主流水线产生持久化事件后，账本会自动填充。",
  recordedWithoutSummary: "已记录，但没有公开摘要",
  selectedRecordInspector: "所选记录检查器",
  recordLabel: "{{kind}}记录",
  inspector: "检查器",
  selectAnyRecord: "请选择一条记录",
  selectAnyRecordDetail:
    "打开机会、Agent 运行、委员会事件、表达或影子持仓，检查其持久化记录。",
  savedSystemRecord: "已保存的系统记录 · 不包含私有思维链",
  brief: "摘要",
  evidence: "证据",
  record: "原始记录",
  normalizedJson: "标准化 JSON",
  researchBoundary: "仅限研究 · 影子环境 · 资金已禁用",
  decisionPacket: "决策数据包",
  noPublicBrief: "此记录尚未保存公开摘要。",
  independentAssessments: "独立评估",
  noRecommendation: "没有建议摘要",
  scoreConfidence: "评分 {{score}} · 置信度 {{confidence}}",
  committeeExchange: "委员会交流",
  provenance: "来源与谱系",
  evidenceReferences: "证据引用",
  noneSaved: "未保存",
  artifacts: "产物",
  committeeRecords: "委员会记录",
  artifactNumber: "产物 {{number}}",
  hash: "哈希 {{hash}}…",
  hashUnavailable: "哈希不可用",
  noArtifact: "所选记录未附带运行产物；机会证据可能体现在评估和委员会事件中。",
  noPublicSummary: "没有公开摘要",
  loadingDurableRecord: "正在载入持久化记录…",
  originalArtifact: "原始保存产物",
  recentEventReplay: "近期事件回放",
  replayRibbon: "回放时间带",
  loadedDurableEvents: "已载入 {{count}} 条持久化事件",
  waitingForEvents: "等待事件",
  noReplayRange: "没有可回放范围",
  replayLoadedHistory: "回放已载入的决策历史",
  live: "实时",
  replayMode: "回放",
  waitingFirstEvent: "等待第一条事件",
  pauseReplay: "暂停回放",
  playReplay: "播放回放",
  playLoadedHistory: "播放已载入历史",
  liveNow: "回到实时",
  liveOpportunityFlow: "实时机会流",
  opportunityFlowStage: "机会流阶段",
  discovery: "发现",
  foundry: "机会铸造",
  committee: "委员会",
  audit: "审计",
  unclassified: "未分类",
  noCandidates: "尚无候选机会",
  building: "构建中",
  foundryWaiting: "机会铸造等待候选输入",
  modelPending: "等待模型",
  assessments: "评估",
  arguments: "论点",
  expressionAudit: "表达与审计",
  selectedCarrier: "所选载体",
  noExpression: "尚未选择表达方式",
  auditBoundary: "审计边界",
  waiting: "等待中",
  shadowObservation: "影子观察",
  noPosition: "没有持仓",
  activeRecentlyUpdated: "活动中或刚刚更新",
  waitingHistorical: "等待中或历史记录",
  savedArtifactsTruth: "不会暴露私有思维链；已保存的产物和交接记录可见。",
  handoffLabel: "从 {{source}} 交接至 {{target}}{{time}}",
  start: "启动",
  stop: "停止",
  restart: "重启",
  runtimeControls: "研究运行时控制",
  startRuntimeAria: "启动研究运行时",
  startRuntimeTip: "准备并启动影子研究服务",
  restartRuntimeAria: "重启研究运行时",
  restartRuntimeTip: "重启研究服务",
  stopRuntimeAria: "停止研究运行时",
  stopRuntimeConfirm: "停止研究运行时？",
  restartRuntimeConfirm: "重启研究运行时？",
  stopRuntimeDetail:
    "ALTA 将停止 Agent 服务、监督进程、PostgreSQL 和 Redis；本机控制台外壳会继续可用，便于再次启动。",
  restartRuntimeDetail:
    "自主服务将重启并等待就绪；此控制台不提供任何资金或经纪商路径。",
  cancel: "取消",
  stopSafely: "安全停止",
  observationNotBrokerage: "仅供观察，不是经纪交易",
  observationNotBrokerageDetail:
    "每一行都是研究用途的影子持仓；此控制台不暴露资金或实盘下单路径。",
  forwardAlphaEvidence: "前瞻 Alpha 证据",
  forwardAlphaDetail:
    "基于入场时冻结决策，相对 SPY 衡量扣除成本后的影子结果。这是证据账本，不是业绩宣称。",
  comparableCloses: "可比已平仓样本",
  minimum: "最低 {{count}} 个",
  moreBeforeCalibration: "再积累 {{count}} 个样本后，校准才可影响预测。",
  calibrationReached: "已达到最低校准样本量；滚动证据现已约束预测。",
  meanRealizedAlpha: "平均已实现 Alpha",
  forecastMae: "预测平均绝对误差",
  forecastMaeDetail: "可比股票直接表达预测的绝对误差。",
  directionalHitRate: "方向命中率",
  directionalHitDetail: "仅作描述；零预测和零结果不计入。",
  forecastReserve: "预测准备金",
  forecastReserveInactive: "样本尚不成熟，当前不启用。",
  forecastReserveActive: "在计算成本前，从新机会预期 Alpha 中扣除。",
  capitalPosture: "资金姿态",
  capitalPostureDetail: "采用最严格的前瞻证据乘数；绝不会增加杠杆。",
  observedLifecycleQuality: "已观察的生命周期质量",
  observedLifecycleDetail:
    "可执行的退出观察将机会质量、路径风险和退出捕获分开衡量，但绝不会自动触发退出。",
  measured: "已衡量 {{count}} 个",
  meanFavorableExcursion: "平均最大有利波动",
  meanAdverseExcursion: "平均最大不利波动",
  meanExitCapture: "平均退出捕获率",
  positivePathMissed: "错过正向路径比例",
  noClosedSample: "尚无已平仓且包含基准对照的影子样本。",
  lastMeasured: "最近衡量于 {{time}}",
  instrument: "标的",
  status: "状态",
  quantity: "数量",
  opened: "开仓时间",
  expression: "表达",
  noShadowPositions: "当前没有已开仓或近期已平仓的影子持仓。",
  awaitingIndependentCloses: "等待足够的独立平仓样本",
  candidates: "候选机会",
  recentFoundryInputs: "近期机会铸造输入",
  opportunities: "机会",
  deduplicatedTheses: "已去重的交易论点",
  agentRoles: "Agent 角色",
  persistentMinds: "{{count}} 个持久化思维",
  expressions: "表达",
  auditedCarriers: "经审计的机会载体",
  shadowPositions: "影子持仓",
  eventCursor: "事件游标",
  appendOnlyLedger: "仅追加账本",
  sourcePosture: "数据源姿态",
  observed: "已观察",
  noSourcePosture: "尚未记录数据源姿态。",
  traderMinds: "Trader 思维",
  minds: "{{count}} 个思维",
  noRollingSummarySaved: "未保存滚动摘要",
  dashboardRenderFailed: "控制台视图无法渲染",
  dashboardRenderFailedDetail:
    "研究运行时未受影响。请重新载入本机控制台，以持久化后端状态重建浏览器视图。",
  reloadConsole: "重新载入控制台",
  credentials: "API 凭据",
  secureProviderConfiguration: "安全的供应商配置",
  secureConfiguration: "安全配置",
  providerCredentials: "供应商 API 凭据",
  credentialCenterDetail:
    "无需翻找后端文件，即可配置模型、行情、新闻和研究供应商。",
  credentialSummary: "凭据概览",
  configured: "已配置",
  supported: "已支持",
  refresh: "刷新",
  credentialChangesLocked: "ALTA 运行期间已锁定凭据修改",
  stopBeforeCredentialChange:
    "更换凭据前请先停止研究运行时，避免同一活动周期混用不同供应商状态。",
  credentialCenterUnavailable: "凭据中心需要处理",
  credentialRefreshFailed: "无法刷新凭据目录。",
  credentialSaveFailed: "凭据未保存。",
  credentialStored: "凭据已保存",
  credentialMissing: "需要凭据",
  trading: "交易",
  paperExecutionDisabled: "模拟盘执行已禁用",
  notConfigured: "未配置",
  source: "来源",
  safeFingerprint: "安全指纹",
  activation: "生效时间",
  nextRuntimeStart: "下次启动运行时",
  notActive: "尚未启用",
  newProviderToken: "新的供应商 Token",
  pasteTokenPlaceholder: "粘贴新 Token——之后不会再次显示",
  environmentCredentialLocked:
    "此凭据来自环境变量；必须先取消该环境变量，才能替换外部凭据。",
  writeOnlyCredentialHelp:
    "只写不读：ALTA 校验后会将凭据以仅限当前用户访问的权限保存在仓库之外。",
  secretNeverReturned: "密钥绝不会返回浏览器",
  savingSecurely: "正在安全保存…",
  saveAndActivate: "保存并在下次启动生效",
  credentialSaved: "凭据已保存。",
  credentialSavedDetail: "输入框已清空，新的安全指纹已经显示。",
  selectProvider: "选择一个供应商，查看其安全配置状态。",
  paperBoundaryTitle: "交易仍隔离在独立的模拟盘安全边界之后",
  paperBoundaryDetail:
    "当前研究版本不接收券商凭据，也不提供实盘下单控件。界面列出 Tiger Trade 是为了明确展示边界，而不是隐藏它。",
  purposeDeepseek: "主要 Agent 推理与研究",
  purposeXai: "独立辩论与联网研究",
  purposeKimi: "独立分析与长上下文研究",
  purposeMassive: "美国股票与期权行情数据",
  purposeFinlight: "标准化市场新闻",
  purposeBrave: "开放互联网搜索",
  purposeJina: "网页正文提取",
  purposeOpenalex: "学术与研究发现",
  yes: "是",
  no: "否",
  unavailable: "—",
};

const domainZh: Record<string, string> = {
  action: "执行",
  active: "活动中",
  advance: "推进",
  agent: "Agent",
  append: "追加",
  argument: "论点",
  assessment: "评估",
  audit: "审计",
  bounded: "受限",
  candidate: "候选机会",
  caution: "谨慎",
  challenge: "质疑",
  collecting: "收集中",
  committee: "委员会",
  complete: "完成",
  completed: "已完成",
  closed: "已关闭",
  conditional: "有条件通过",
  current: "当前",
  degraded: "降级",
  deliberation: "审议",
  disabled: "已禁用",
  disconfirming: "反证",
  discussion: "讨论",
  discovery: "发现",
  event: "事件",
  evidence: "证据",
  expression: "表达",
  expressed: "已表达",
  failed: "失败",
  foundry: "机会铸造",
  fundamental: "基本面",
  healthy: "健康",
  hold: "暂缓",
  idle: "空闲",
  insufficient: "不足",
  live: "实时",
  locked: "已锁定",
  market: "市场",
  measured: "已衡量",
  mind: "思维",
  moderator: "主持",
  neutral: "中性",
  negative: "负向",
  not: "未",
  observed: "已观察",
  observing: "观察中",
  offline: "离线",
  online: "在线",
  opportunity: "机会",
  open: "已开启",
  options: "期权",
  pending: "待处理",
  position: "持仓",
  positive: "正向",
  preservation: "保全",
  probation: "观察期",
  ranked: "已排序",
  ready: "就绪",
  recorded: "已记录",
  recovering: "恢复中",
  restart: "重启",
  reject: "拒绝",
  rejected: "已拒绝",
  review: "评审",
  run: "运行",
  running: "运行中",
  scout: "侦察",
  shadow: "影子",
  started: "已开始",
  start: "启动",
  stock: "股票",
  stop: "停止",
  stopped: "已停止",
  succeeded: "成功",
  structural: "结构性",
  thesis: "主论点",
  under: "正在",
  validated: "已验证",
  volatility: "波动率",
  waiting: "等待中",
  wait: "等待",
};

const exactDomainZh: Record<string, string> = {
  "append only": "仅追加",
  "capital disabled": "资金已禁用",
  "committee moderator": "委员会主持",
  "defined risk options": "风险限定期权",
  "direct stock": "直接持有股票",
  "expectation gap scout": "预期差侦察",
  "expression & audit": "表达与审计",
  "fundamental change": "基本面变化",
  "insufficient sample": "样本不足",
  "attempt count": "尝试次数",
  "confidence": "置信度",
  "direction": "方向",
  "falsifier": "证伪条件",
  "foundry state": "铸造状态",
  "horizon days": "预期周期（天）",
  "kind": "类型",
  "known at": "记录时间",
  "latency ms": "延迟（毫秒）",
  "market neutral basket": "市场中性篮子",
  "market data": "行情数据",
  "models": "模型",
  "news": "新闻",
  "research": "研究",
  "environment": "环境变量",
  "external": "外部安全文件",
  "missing": "未配置",
  "market dislocation scout": "市场错位侦察",
  "mechanism": "作用机制",
  "model id": "模型标识",
  "model provider": "模型供应商",
  "not measured": "尚未衡量",
  "rationale": "理由",
  "recommendation": "建议",
  "runtime ready": "运行时就绪",
  "runtime recovering": "运行时恢复中",
  "runtime stopped": "运行时已停止",
  "causal policy scout": "因果政策侦察",
  "change event scout": "变化事件侦察",
  "console reconnecting": "控制台重连中",
  "short dated skew normalization": "短期期权偏斜回归",
  "structural flow": "结构性资金流",
  "status": "状态",
  "symbol": "标的",
  "under review": "评审中",
  "volatility surface": "波动率曲面",
  "why now": "为何是现在",
};

function initialLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "zh-CN") return stored;
  } catch {
    // Storage is optional. Browser preference remains a safe default.
  }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

function interpolate(
  template: string,
  values?: Record<string, string | number>,
) {
  if (!values) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) =>
    values[key] === undefined ? `{{${key}}}` : String(values[key]),
  );
}

function humanize(value: string) {
  return value
    .replaceAll(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll(/[._-]+/g, " ")
    .replaceAll(/\b\w/g, (letter) => letter.toUpperCase());
}

function localizeDomainValue(value: string, locale: Locale) {
  if (locale === "en") return humanize(value);
  const normalized = value
    .trim()
    .replaceAll(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .replaceAll(/[._-]+/g, " ");
  if (exactDomainZh[normalized]) return exactDomainZh[normalized];
  const translated = normalized
    .split(/\s+/)
    .map((token) => domainZh[token] ?? token)
    .join(" · ");
  return translated === normalized ? value : translated;
}

const systemMessageZh: Record<string, string> = {
  "The local operator service is temporarily unreachable.":
    "本机操作服务暂时无法访问。",
  "The dashboard build and local operator service use different protocol versions. Rebuild the dashboard and restart the console.":
    "控制台构建版本与本机操作服务的协议版本不一致。请重新构建控制台并重启服务。",
  "This device is offline. ALTA will reconnect automatically.":
    "此设备已离线；ALTA 会自动重新连接。",
  "Runtime stopped — showing the last synchronized research snapshot.":
    "运行时已停止——当前显示上次同步的研究快照。",
  "Controls are disabled in synthetic preview": "合成数据预览中已禁用控制功能",
  "The secure console session is not ready yet": "安全控制台会话尚未就绪",
  "Alpha is unproven: the forward Shadow sample is below the minimum.":
    "Alpha 尚未得到证明：前瞻影子样本量低于最低要求。",
};

type I18nContextValue = {
  locale: Locale;
  toggleLocale: () => void;
  t: (key: MessageKey, values?: Record<string, string | number>) => string;
  domain: (value: string) => string;
  relative: (value?: string) => string;
  clock: (value?: string) => string;
  number: (value?: number, options?: Intl.NumberFormatOptions) => string;
  value: (value: unknown) => string;
  systemMessage: (message: string | null | undefined) => string | null;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
    document.title =
      locale === "zh-CN" ? "ALTA 操作控制台" : "ALTA Operator Console";
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // Locale remains active for this session if storage is unavailable.
    }
  }, [locale]);

  const toggleLocale = useCallback(
    () => setLocale((current) => (current === "en" ? "zh-CN" : "en")),
    [],
  );

  const context = useMemo<I18nContextValue>(() => {
    const dictionary = locale === "zh-CN" ? zhCN : en;
    const t = (key: MessageKey, values?: Record<string, string | number>) =>
      interpolate(dictionary[key], values);
    const number = (value?: number, options?: Intl.NumberFormatOptions) =>
      value === undefined
        ? t("unavailable")
        : new Intl.NumberFormat(locale, options).format(value);
    return {
      locale,
      toggleLocale,
      t,
      domain: (value) => localizeDomainValue(value, locale),
      relative: (value) => {
        if (!value) return t("unavailable");
        const seconds = Math.round(
          (new Date(value).getTime() - Date.now()) / 1000,
        );
        const formatter = new Intl.RelativeTimeFormat(locale, {
          numeric: "auto",
        });
        if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
        const minutes = Math.round(seconds / 60);
        if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
        const hours = Math.round(minutes / 60);
        if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
        return formatter.format(Math.round(hours / 24), "day");
      },
      clock: (value) =>
        value
          ? new Intl.DateTimeFormat(locale, {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }).format(new Date(value))
          : t("unavailable"),
      number,
      value: (value) => {
        if (value === null || value === undefined || value === "")
          return t("unavailable");
        if (typeof value === "boolean") return value ? t("yes") : t("no");
        if (typeof value === "number") return number(value);
        if (typeof value === "object") return JSON.stringify(value, null, 2);
        return String(value);
      },
      systemMessage: (message) => {
        if (!message) return null;
        return locale === "zh-CN"
          ? (systemMessageZh[message] ?? message)
          : message;
      },
    };
  }, [locale, toggleLocale]);

  return (
    <I18nContext.Provider value={context}>{children}</I18nContext.Provider>
  );
}

// The provider and its hook intentionally share one private context so no
// caller can import or mutate the context directly.
// oxlint-disable-next-line react/only-export-components
export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside LocaleProvider");
  return context;
}
