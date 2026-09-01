function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`Tiger Paper returned an invalid ${label}`);
  return value;
}

function count(value, label) {
  if (!Number.isInteger(value) || value < 0)
    throw new Error(`Tiger Paper returned an invalid ${label}`);
  return value;
}

function boundedString(value, label, pattern, { nullable = false } = {}) {
  if (nullable && value === null) return null;
  if (typeof value !== "string" || !pattern.test(value))
    throw new Error(`Tiger Paper returned an invalid ${label}`);
  return value;
}

function decimal(value, label) {
  return boundedString(value, label, /^-?\d+(?:\.\d+)?$/, { nullable: true });
}

function timestamp(value, label) {
  if (value === null) return null;
  if (
    typeof value !== "string" ||
    value.length > 40 ||
    !Number.isFinite(Date.parse(value))
  )
    throw new Error(`Tiger Paper returned an invalid ${label}`);
  return value;
}

function capitalPosition(value) {
  const position = object(value, "position");
  return {
    symbol: boundedString(
      position.symbol,
      "position symbol",
      /^[A-Z][A-Z0-9.-]{0,14}$/,
    ),
    securityType: boundedString(
      position.securityType,
      "security type",
      /^[A-Z0-9_]{1,16}$/,
    ),
    currency: boundedString(
      position.currency,
      "position currency",
      /^[A-Z]{3,8}$/,
    ),
    quantity: decimal(position.quantity, "position quantity"),
    averageCost: decimal(position.averageCost, "average cost"),
    marketPrice: decimal(position.marketPrice, "market price"),
    marketValue: decimal(position.marketValue, "market value"),
    unrealizedPnl: decimal(position.unrealizedPnl, "unrealized PnL"),
    unrealizedPnlPercent: decimal(
      position.unrealizedPnlPercent,
      "unrealized PnL percent",
    ),
    realizedPnl: decimal(position.realizedPnl, "realized PnL"),
    todayPnl: decimal(position.todayPnl, "today PnL"),
    salableQuantity: decimal(position.salableQuantity, "salable quantity"),
  };
}

function capitalOrder(value) {
  const order = object(value, "order");
  if (typeof order.outsideRegularHours !== "boolean")
    throw new Error("Tiger Paper returned an invalid outside-hours flag");
  return {
    reference: boundedString(
      order.reference,
      "order reference",
      /^[a-f0-9]{16}$/,
    ),
    symbol: boundedString(
      order.symbol,
      "order symbol",
      /^[A-Z][A-Z0-9.-]{0,14}$/,
    ),
    securityType: boundedString(
      order.securityType,
      "order security type",
      /^[A-Z0-9_]{1,16}$/,
    ),
    side: boundedString(order.side, "order side", /^[A-Z0-9_.-]{1,16}$/),
    orderType: boundedString(
      order.orderType,
      "order type",
      /^[A-Z0-9_.-]{1,16}$/,
    ),
    status: boundedString(order.status, "order status", /^[A-Z0-9_.-]{1,32}$/),
    quantity: decimal(order.quantity, "order quantity"),
    filled: decimal(order.filled, "filled quantity"),
    remaining: decimal(order.remaining, "remaining quantity"),
    limitPrice: decimal(order.limitPrice, "limit price"),
    averageFillPrice: decimal(order.averageFillPrice, "average fill price"),
    commission: decimal(order.commission, "commission"),
    realizedPnl: decimal(order.realizedPnl, "order realized PnL"),
    timeInForce: boundedString(
      order.timeInForce,
      "time in force",
      /^[A-Z0-9_.-]{0,12}$/,
    ),
    outsideRegularHours: order.outsideRegularHours,
    createdAt: timestamp(order.createdAt, "order creation time"),
    updatedAt: timestamp(order.updatedAt, "order update time"),
    filledAt: timestamp(order.filledAt, "order fill time"),
  };
}

export function sanitizeCapitalSnapshot(value) {
  const payload = object(value, "result");
  if (payload.paper !== true || payload.accountBinding !== true)
    throw new Error(
      "Tiger Paper preflight did not prove Paper account binding",
    );
  if (!Array.isArray(payload.positions) || !Array.isArray(payload.orders))
    throw new Error("Tiger Paper returned an invalid portfolio snapshot");
  const positions = payload.positions.map(capitalPosition);
  const orders = payload.orders.map(capitalOrder);
  const positionCount = count(payload.positionCount, "position count");
  const recentOrderCount = count(
    payload.recentOrderCount,
    "recent-order count",
  );
  if (positionCount !== positions.length || recentOrderCount !== orders.length)
    throw new Error("Tiger Paper portfolio counts do not match the snapshot");
  const assets = object(payload.assets, "asset summary");
  const observedAt = timestamp(payload.observedAt, "observation time");
  if (observedAt === null)
    throw new Error("Tiger Paper returned an invalid observation time");
  return {
    paper: true,
    accountBinding: true,
    accountFingerprint: boundedString(
      payload.accountFingerprint,
      "account fingerprint",
      /^[a-f0-9]{12}$/,
    ),
    observedAt,
    brokerUpdatedAt: timestamp(payload.brokerUpdatedAt, "broker update time"),
    positionCount,
    openOrderCount: count(payload.openOrderCount, "open-order count"),
    recentOrderCount,
    mutationPolicy: boundedString(
      payload.mutationPolicy,
      "mutation policy",
      /^risk_budgeted_limit_day_v1$/,
    ),
    maxOrderNotional: decimal(
      payload.maxOrderNotional,
      "maximum order notional",
    ),
    assets: {
      currency: boundedString(
        assets.currency,
        "asset currency",
        /^[A-Z]{3,8}$/,
      ),
      cashBalance: decimal(assets.cashBalance, "cash balance"),
      cashAvailableForTrade: decimal(
        assets.cashAvailableForTrade,
        "cash available for trade",
      ),
      netLiquidation: decimal(assets.netLiquidation, "net liquidation"),
      grossPositionValue: decimal(
        assets.grossPositionValue,
        "gross position value",
      ),
      buyingPower: decimal(assets.buyingPower, "buying power"),
      unrealizedPnl: decimal(assets.unrealizedPnl, "asset unrealized PnL"),
      realizedPnl: decimal(assets.realizedPnl, "asset realized PnL"),
      maintenanceMargin: decimal(
        assets.maintenanceMargin,
        "maintenance margin",
      ),
    },
    positions,
    orders,
  };
}
