import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { resolveLocale, type Locale } from "./locale";
import zhHK from "./locales/zh-HK.json";
import hkDomain from "./locales/zh-HK-domain.json";
import en from "./locales/en.json";
import zhCN from "./locales/zh-CN.json";
export type { Locale } from "./locale";

const STORAGE_KEY = "alta.console.locale";

type MessageKey = keyof typeof en;

const domainZh: Record<string, string> = {
  forming: "整合中",
  assessor: "评估员",
  skipped: "已跳过",
  action: "执行",
  active: "活动中",
  advance: "推进",
  agent: "Agent",
  append: "追加",
  argument: "论点",
  assessment: "评估",
  audit: "审计",
  balanced: "均衡",
  bounded: "受限",
  candidate: "候选机会",
  caution: "谨慎",
  challenge: "质疑",
  collecting: "收集中",
  committee: "委员会",
  concentrated: "集中",
  complete: "完成",
  completed: "已完成",
  closed: "已关闭",
  conditional: "有条件通过",
  current: "当前",
  unknown: "时效未验证",
  expired: "已过期",
  invalid: "无效",
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
  "alpha source": "Alpha 来源",
  "capital disabled": "资金已禁用",
  "authorization invalid": "授权状态无效",
  "configuration changed": "配置已变化",
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
  "systematic exposure": "系统性暴露",
  "underlying": "底层标的",
  "catalyst": "催化剂",
  "growth duration": "增长久期",
  "market beta": "市场 Beta",
  "earnings revision": "盈利预期修正",
  "relative value": "相对价值",
  "market and regulatory": "市场与监管",
  "news and discovery": "新闻与发现",
  "research and social": "研究与社交",
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
  "not configured": "尚未配置",
  "paper enabled": "模拟盘权限已生效",
  "paper recovery required": "模拟盘恢复中",
  "paper ready disabled": "模拟盘就绪但未授权",
  "rationale": "理由",
  "recommendation": "建议",
  "runtime ready": "运行时就绪",
  "runtime recovering": "运行时恢复中",
  "runtime stopped": "运行时已停止",
  "causal policy scout": "因果政策侦察",
  "change event scout": "变化事件侦察",
  "continue lead": "连续研究席位",
  "console reconnecting": "控制台重连中",
  "expand coverage": "扩展覆盖席位",
  "short dated skew normalization": "短期期权偏斜回归",
  "structural flow": "结构性资金流",
  "status": "状态",
  "snapshot invalid": "券商快照无效",
  "symbol": "标的",
  "under review": "评审中",
  "unconstrained": "自由探索席位",
  "volatility surface": "波动率曲面",
  "why now": "为何是现在",
};

function initialLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return resolveLocale(stored, navigator.languages ?? [navigator.language]);
  } catch {
    // Storage is optional. Browser preference remains a safe default.
  }
  return resolveLocale(null, navigator.languages ?? [navigator.language]);
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
  const exact: Record<string, string> =
    locale === "zh-HK" ? hkDomain.exact : exactDomainZh;
  const words: Record<string, string> =
    locale === "zh-HK" ? hkDomain.domain : domainZh;
  const normalized = value
    .trim()
    .replaceAll(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .replaceAll(/[._-]+/g, " ");
  if (exact[normalized]) return exact[normalized];
  const translated = normalized
    .split(/\s+/)
    .map((token) => words[token] ?? token)
    .join(" · ");
  return translated === normalized ? value : translated;
}

const systemMessageZh: Record<string, string> = {
  "The local service returned an invalid response. The last valid snapshot is preserved; ALTA will retry.":
    "本机服务返回了无效数据。已保留上次有效快照，ALTA 将自动重试。",
  "The local service did not respond before the timeout.":
    "本机服务响应超时，将自动重试。",
  "Research storage is temporarily unavailable.":
    "研究数据库暂时不可用，将自动重试。",
  "The research service is temporarily unreachable.":
    "研究服务暂时无法访问，将自动重试。",
  "The research service did not respond before the timeout.":
    "研究服务响应超时，将自动重试。",
  "The research response exceeded the console safety limit.":
    "研究数据响应超出控制台安全大小限制，请缩小查询范围。",
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
  "The unadjusted Alpha interval is positive, but it does not survive the opportunity-search selection correction.":
    "未调整的 Alpha 区间为正，但未能通过机会搜索选择偏差校正。",
  "The selection-adjusted confidence bound remains forward Shadow evidence; regime dependence and non-normal returns still require external validation.":
    "选择偏差调整后的置信下界仍只是前瞻 Shadow 证据；市场状态依赖与非正态收益仍需外部验证。",
  "Execution quality is unavailable until a position has a complete forward open and close fill.":
    "只有持仓完成前向开仓与平仓成交后，才能衡量执行质量。",
  "Execution TCA is based on forward Shadow quotes and modeled fills; it is not live-market capacity or broker performance.":
    "执行 TCA 基于前向 Shadow 报价和模型成交，不代表真实市场容量或经纪商执行表现。",
};

function localizeSystemMessage(message: string, locale: Locale) {
  const tiger = message.match(
    /^Tiger Paper preflight failed: ([A-Za-z0-9_.-]+)(?:\[([A-Za-z0-9_.-]+)\])?:([a-f0-9]{16,64})$/,
  );
  if (tiger) {
    const [, errorType, brokerCode, fingerprint] = tiger;
    if (locale !== "en") {
      const reason =
        locale === "zh-HK"
          ? brokerCode === "1000"
            ? "券商未能通過共用參數驗證；請核對 Tiger ID、模擬盤戶口、系統時間，以及與已登記公鑰配對的私鑰"
            : "券商拒絕了模擬盤驗證要求"
          : brokerCode === "1000"
            ? "券商拒绝了公共参数校验；请检查 Tiger ID、模拟盘账户、系统时间和已登记公钥对应的私钥"
            : "券商拒绝了模拟盘验证请求";
      return locale === "zh-HK"
        ? `${reason}（錯誤 ${brokerCode ?? errorType}，診斷指紋 ${fingerprint.slice(0, 16)}）`
        : `${reason}（错误 ${brokerCode ?? errorType}，诊断指纹 ${fingerprint.slice(0, 16)}）`;
    }
    const reason =
      brokerCode === "1000"
        ? "The broker rejected common-parameter validation; check Tiger ID, the Paper account, system time, and the private key paired with the registered public key"
        : "The broker rejected the Paper verification request";
    return `${reason} (error ${brokerCode ?? errorType}, diagnostic fingerprint ${fingerprint.slice(0, 16)})`;
  }
  if (locale === "en") return message;
  const messages: Record<string, string> =
    locale === "zh-HK" ? hkDomain.system : systemMessageZh;
  return messages[message] ?? message;
}

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
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
      locale === "zh-HK"
        ? "ALTA 操作控制台"
        : locale === "zh-CN"
          ? "ALTA 操作控制台"
          : "ALTA Operator Console";
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // Locale remains active for this session if storage is unavailable.
    }
  }, [locale]);

  const context = useMemo<I18nContextValue>(() => {
    const dictionary: Record<MessageKey, string> =
      locale === "zh-HK" ? zhHK : locale === "zh-CN" ? zhCN : en;
    const numberFormatter = new Intl.NumberFormat(locale);
    const relativeFormatter = new Intl.RelativeTimeFormat(locale, {
      numeric: "auto",
    });
    const clockFormatter = new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    const t = (key: MessageKey, values?: Record<string, string | number>) =>
      interpolate(dictionary[key], values);
    const number = (value?: number, options?: Intl.NumberFormatOptions) =>
      value === undefined
        ? t("unavailable")
        : (options
            ? new Intl.NumberFormat(locale, options)
            : numberFormatter
          ).format(value);
    return {
      locale,
      setLocale,
      t,
      domain: (value) => localizeDomainValue(value, locale),
      relative: (value) => {
        if (!value) return t("unavailable");
        const timestamp = new Date(value).getTime();
        if (!Number.isFinite(timestamp)) return t("unavailable");
        const seconds = Math.round((timestamp - Date.now()) / 1000);
        const formatter = relativeFormatter;
        if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
        const minutes = Math.round(seconds / 60);
        if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
        const hours = Math.round(minutes / 60);
        if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
        return formatter.format(Math.round(hours / 24), "day");
      },
      clock: (value) => {
        if (!value) return t("unavailable");
        const timestamp = new Date(value).getTime();
        if (!Number.isFinite(timestamp)) return t("unavailable");
        return clockFormatter.format(timestamp);
      },
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
        return localizeSystemMessage(message, locale);
      },
    };
  }, [locale]);

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
