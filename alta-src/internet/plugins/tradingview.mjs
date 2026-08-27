import { defineTool } from "./support.mjs";

const ORIGINS = {
  global: "https://www.tradingview.com",
  china: "https://cn.tradingview.com",
};
const MARKETS = {
  usa: "stocks-usa",
  china: "stocks-china",
  hong_kong: "stocks-hong-kong",
  india: "stocks-india",
  japan: "stocks-japan",
  uk: "stocks-uk",
  germany: "stocks-germany",
};
const INTERVALS = [
  "1T",
  "10T",
  "100T",
  "1000T",
  "1S",
  "5S",
  "10S",
  "15S",
  "30S",
  "45S",
  "1",
  "2",
  "3",
  "5",
  "10",
  "15",
  "30",
  "45",
  "60",
  "120",
  "180",
  "240",
  "D",
  "W",
  "M",
  "3M",
  "6M",
  "12M",
];
const SYMBOL_ROUTES = {
  symbol: "",
  technicals: "technicals/",
  symbol_ideas: "ideas/",
  symbol_news: "news/",
  financials: "financials-overview/",
  income: "financials-income-statement/",
  balance: "financials-balance-sheet/",
  cash_flow: "financials-cash-flow/",
  statistics: "financials-statistics-and-ratios/",
  dividends: "financials-dividends/",
  financial_earnings: "financials-earnings/",
  revenue: "financials-revenue/",
  earnings: "earnings/",
  forecast: "forecast/",
  actuals: "forecast-actuals-and-estimates/",
  seasonals: "seasonals/",
  options: "options/",
};
const ROOT_ROUTES = {
  economic_calendar: "/economic-calendar/",
  earnings_global: "/earnings-calendar/",
  revenue_calendar: "/revenue-calendar/",
  dividends_global: "/dividend-calendar/",
  ipo_calendar: "/ipo-calendar/",
  screener: "/screener/",
  crypto_screener: "/crypto-coins-screener/",
  etf_screener: "/etf-screener/",
  bond_screener: "/bond-screener/",
  cex_screener: "/cex-screener/",
  dex_screener: "/dex-screener/",
  stock_heatmap: "/heatmap/stock/",
  etf_heatmap: "/heatmap/etf/",
  crypto_heatmap: "/heatmap/crypto/",
  yield_curves: "/yield-curves/",
  macro_maps: "/macro-maps/",
  news: "/news/",
  community: "/ideas/",
  markets: "/markets/",
  crypto: "/markets/cryptocurrencies/",
  forex: "/markets/currencies/",
  futures: "/markets/futures/",
  bonds: "/markets/bonds/",
  etfs: "/markets/etfs/",
  world_economy: "/markets/world-economy/",
  economy_indicators: "/markets/world-economy/indicators/",
  economy_heatmap: "/markets/world-economy/indicators-heatmap/",
};
const ACTIONS = [
  "chart",
  "bundle",
  ...Object.keys(SYMBOL_ROUTES),
  ...Object.keys(ROOT_ROUTES),
  "earnings_calendar",
  "dividends_calendar",
];
const ACTION_SET = new Set(ACTIONS);
const ARGUMENTS = new Set(["action", "symbol", "interval", "locale", "market"]);
const BUNDLE_PAGES = {
  overview: "",
  technicals: "technicals/",
  financials: "financials-overview/",
  forecast: "forecast/",
  news: "news/",
};
const CHART_ACTIONS = new Set(["chart", "bundle"]);
const MARKET_ACTIONS = new Set(["earnings_calendar", "dividends_calendar"]);
const SYMBOL_ACTIONS = new Set([
  ...CHART_ACTIONS,
  ...Object.keys(SYMBOL_ROUTES),
]);
const RESULT_LIMIT_BYTES = 900;
const DISPLAY_NOTICE =
  "Open this page for human-readable display; do not send it to ALTA fetch, batch-fetch, crawl, research, sitemap, feed, social-read, or archive tools.";
const BUNDLE_NOTICE =
  "Open manually; do not pass TradingView URLs to ALTA readers.";

function invalid(message) {
  throw Object.assign(new Error(message), {
    status: 400,
    code: "alta_tradingview_invalid_argument",
  });
}

function tradingViewSymbol(value) {
  const raw = String(value ?? "");
  if (raw.length > 89)
    invalid("symbol must use a bounded EXCHANGE:TICKER identifier");
  const symbol = raw.trim().toUpperCase();
  if (!/^[A-Z0-9_]{1,24}:[A-Z0-9][A-Z0-9._^!-]{0,63}$/.test(symbol))
    invalid("symbol must use a bounded EXCHANGE:TICKER identifier");
  return symbol;
}

function symbolUrl(origin, action, symbol, interval) {
  if (action === "chart") {
    const url = new URL("/chart/", origin);
    url.searchParams.set("symbol", symbol);
    if (interval) url.searchParams.set("interval", interval);
    return url.href;
  }
  const slug = encodeURIComponent(symbol.replace(":", "-"));
  return new URL(`/symbols/${slug}/${SYMBOL_ROUTES[action]}`, origin).href;
}

function boundedResult(result) {
  if (Buffer.byteLength(JSON.stringify(result)) > RESULT_LIMIT_BYTES)
    throw Object.assign(
      new Error("TradingView navigation result is too large"),
      {
        status: 500,
        code: "alta_tradingview_result_limit",
      },
    );
  return result;
}

function navigate(_service, args) {
  if (Object.keys(args).some((name) => !ARGUMENTS.has(name)))
    invalid("Unsupported TradingView argument");
  const action = String(args.action ?? "");
  if (!ACTION_SET.has(action)) invalid("Unsupported TradingView view");
  if (args.locale !== undefined && !Object.hasOwn(ORIGINS, args.locale))
    invalid("Unsupported TradingView locale");
  if (args.market !== undefined && !Object.hasOwn(MARKETS, args.market))
    invalid("Unsupported TradingView market");
  if (args.interval !== undefined && !INTERVALS.includes(args.interval))
    invalid("Unsupported TradingView interval");
  const usesSymbol = SYMBOL_ACTIONS.has(action);
  const usesMarket = MARKET_ACTIONS.has(action);
  if (!usesSymbol && args.symbol !== undefined)
    invalid("symbol is only supported for chart and symbol views");
  if (!CHART_ACTIONS.has(action) && args.interval !== undefined)
    invalid("interval is only supported for chart and analysis bundle views");
  if (!usesMarket && args.market !== undefined)
    invalid("market is only supported for earnings and dividends calendars");
  const origin = ORIGINS[args.locale] ?? ORIGINS.global;
  let symbol;
  let url;
  if (usesSymbol) {
    symbol = tradingViewSymbol(args.symbol);
    if (action !== "bundle")
      url = symbolUrl(origin, action, symbol, args.interval);
  } else if (MARKET_ACTIONS.has(action)) {
    const market = MARKETS[args.market] ?? MARKETS.usa;
    const page = action === "earnings_calendar" ? "earnings" : "dividends";
    url = new URL(`/markets/${market}/${page}/`, origin).href;
  } else url = new URL(ROOT_ROUTES[action], origin).href;
  if (action === "bundle")
    return boundedResult({
      source: "tradingview",
      mode: "display_only_navigation",
      action,
      base_url: symbolUrl(origin, "symbol", symbol),
      chart_url: symbolUrl(origin, "chart", symbol, args.interval),
      pages: { ...BUNDLE_PAGES },
      machine_data_tools: ["alta_finance_data", "alta_news_search"],
      notice: BUNDLE_NOTICE,
    });
  const result = {
    source: "tradingview",
    mode: "display_only_navigation",
    action,
    ...(symbol ? { symbol } : {}),
    ...(url ? { url } : {}),
    machine_data_tools: ["alta_finance_data", "alta_news_search"],
    notice: DISPLAY_NOTICE,
  };
  return boundedResult(result);
}

export const tradingViewPlugin = {
  id: "alta-tradingview-navigation",
  tools: [
    defineTool(
      "alta_tradingview_navigate",
      "TradingView",
      "Build TradingView display links; use ALTA finance/news for data.",
      {
        type: "object",
        additionalProperties: false,
        required: ["action"],
        properties: {
          action: { type: "string", enum: ACTIONS },
          symbol: {
            type: "string",
            maxLength: 89,
          },
          interval: {
            type: "string",
            enum: INTERVALS,
          },
          locale: { type: "string", enum: ["global", "china"] },
          market: { type: "string", enum: Object.keys(MARKETS) },
        },
      },
      navigate,
    ),
  ],
};
