import { useMemo, useState } from "react";
import {
  CircleCheck,
  Clock3,
  Landmark,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  UnlockKeyhole,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
import {
  ExecutionModePanel,
  type BrokerCredentialRequest,
} from "./execution-mode-panel";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n";
import type { ControlState, PaperCapitalStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { BrokerConnections } from "./broker-connections";
import type {
  BrokerConnectionRequest,
  BrokerVerification,
} from "@/lib/broker-connections";

type CapitalConsoleProps = {
  capital: PaperCapitalStatus | null;
  error: string | null;
  control: ControlState | null;
  preview: boolean;
  online: boolean;
  onRefresh: () => Promise<void>;
  onAuthorization: (enabled: boolean) => Promise<void>;
  onMode: (mode: "shadow" | "broker_paper", revision: string) => Promise<void>;
  onCredentials: (request: BrokerCredentialRequest) => Promise<void>;
  onBrokerConnection: (
    request: BrokerConnectionRequest,
  ) => Promise<BrokerVerification>;
};

type PendingAction = "refresh" | "disable" | null;

function finite(value: string | null | undefined) {
  if (value === null || value === undefined || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function CapitalConsole({
  capital,
  error,
  control,
  preview,
  online,
  onRefresh,
  onAuthorization,
  onMode,
  onCredentials,
  onBrokerConnection,
}: CapitalConsoleProps) {
  const { clock, domain, locale, relative, systemMessage, t } = useI18n();
  const [pending, setPending] = useState<PendingAction>(null);
  const [confirming, setConfirming] = useState<"disable" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const snapshot = capital?.snapshot ?? null;
  const recoveryOnly = Boolean(
    capital?.closeOnly ||
      capital?.drainRequired ||
      capital?.posture === "paper_recovery_required",
  );
  const ineffectiveRequest = Boolean(
    capital?.requestedEnabled && !capital.enabled,
  );
  const runtimeActive = Boolean(
    control?.runtime.ready ||
      control?.runtime.host?.processAlive ||
      control?.runtime.supervisor?.childProcessAlive ||
      control?.operation?.status === "running",
  );
  const currency = snapshot?.assets.currency || "USD";
  const money = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }),
    [currency, locale],
  );
  const formatMoney = (value: string | null | undefined) => {
    const number = finite(value);
    return number === null ? t("unavailable") : money.format(number);
  };
  const formatPercent = (value: string | null | undefined) => {
    const number = finite(value);
    return number === null
      ? null
      : new Intl.NumberFormat(locale, {
          style: "percent",
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(number);
  };
  const canRevoke = Boolean(
    capital?.requestedEnabled && online && !preview && !pending,
  );

  async function revokeAuthorization() {
    setPending("disable");
    setActionError(null);
    try {
      await onAuthorization(false);
      setConfirming(null);
    } catch (reason) {
      setActionError(
        systemMessage(reason instanceof Error ? reason.message : null) ??
          t("capitalOperationFailed"),
      );
    } finally {
      setPending(null);
    }
  }

  async function refresh() {
    setPending("refresh");
    setActionError(null);
    try {
      await onRefresh();
    } catch (reason) {
      setActionError(
        systemMessage(reason instanceof Error ? reason.message : null) ??
          t("capitalOperationFailed"),
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <Tabs defaultValue="execution" className="capital-workspace">
      <TabsList aria-label={t("capitalWorkspace")}>
        <TabsTrigger value="execution">{t("executionAndAccount")}</TabsTrigger>
        <TabsTrigger value="connections">
          {t("brokerConnectionsTitle")}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="execution">
        <section
          className="capital-console"
          aria-labelledby="capital-console-title"
        >
          <header className="capital-heading">
            <div>
              <h2 id="capital-console-title">{t("capitalAuthorization")}</h2>
              <p>{t("paperCapitalSubtitle")}</p>
            </div>
            <Badge variant="outline" className="paper-badge">
              <ShieldCheck data-icon="inline-start" /> {t("tigerPaper")}
            </Badge>
          </header>

          <ExecutionModePanel
            capital={capital}
            disabled={runtimeActive || !online || preview || pending !== null}
            onMode={onMode}
            onCredentials={onCredentials}
          />

          {(error ||
            actionError ||
            (capital?.requestedEnabled && capital?.configurationError) ||
            capital?.authorizationError ||
            capital?.snapshotError) && (
            <Alert variant="destructive" className="capital-alert">
              <TriangleAlert />
              <AlertTitle>{t("capitalOperationFailed")}</AlertTitle>
              <AlertDescription>
                {actionError ??
                  systemMessage(error) ??
                  capital?.configurationError ??
                  capital?.authorizationError ??
                  capital?.snapshotError}
              </AlertDescription>
            </Alert>
          )}

          <div className="capital-control-plane">
            <div className="capital-gate">
              <div
                className="capital-gate-icon"
                data-enabled={capital?.enabled || undefined}
              >
                {capital?.enabled ? <UnlockKeyhole /> : <LockKeyhole />}
              </div>
              <Field orientation="horizontal" className="capital-switch-field">
                <FieldContent>
                  <FieldLabel>
                    {recoveryOnly
                      ? t("recoveryOnlyAuthorization")
                      : capital?.enabled
                        ? t("authorizationArmed")
                        : t("authorizationDisarmed")}
                  </FieldLabel>
                  <FieldDescription>
                    {recoveryOnly
                      ? t("recoveryOnlyAuthorizationDetail")
                      : t("capitalGateDetail")}
                  </FieldDescription>
                </FieldContent>
                {capital?.enabled && (
                  <Button
                    variant="outline"
                    disabled={!canRevoke}
                    onClick={() => {
                      setConfirming("disable");
                    }}
                  >
                    {t("revokeAuthorization")}
                  </Button>
                )}
              </Field>
              <div className="capital-gate-state" aria-live="polite">
                <Badge
                  variant={
                    recoveryOnly
                      ? "secondary"
                      : capital?.enabled
                        ? "default"
                        : "secondary"
                  }
                >
                  {recoveryOnly
                    ? t("paperRecoveryOnly")
                    : capital?.enabled
                      ? t("capitalEnabled")
                      : t("capitalDisabledSafe")}
                </Badge>
                <span>{domain(capital?.posture ?? "disabled")}</span>
              </div>
              {!capital?.configured && (
                <p className="capital-gate-note">
                  {t("capitalConfigRequired")}
                </p>
              )}
              {!capital?.enabled && runtimeActive && (
                <p className="capital-gate-note">
                  {t("capitalRuntimeStopRequired")}
                </p>
              )}
              {capital?.posture === "configuration_changed" && (
                <p className="capital-gate-note is-warning">
                  {t("configurationChanged")}
                </p>
              )}
              {ineffectiveRequest && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canRevoke}
                  onClick={() => setConfirming("disable")}
                >
                  {t("clearAuthorizationRequest")}
                </Button>
              )}
            </div>

            <dl className="capital-proof-list">
              <div>
                <dt>{t("requestedAuthorization")}</dt>
                <dd>
                  {capital?.requestedEnabled
                    ? t("authorizationRequested")
                    : t("authorizationNotRequested")}
                </dd>
              </div>
              <div>
                <dt>{t("effectiveAuthorization")}</dt>
                <dd>
                  {recoveryOnly
                    ? t("paperRecoveryOnly")
                    : capital?.enabled
                      ? t("effectiveEnabled")
                      : t("effectiveDisabled")}
                </dd>
              </div>
              <div>
                <dt>{t("lastVerified")}</dt>
                <dd>
                  {capital?.lastPreflightAt
                    ? relative(capital.lastPreflightAt)
                    : t("unavailable")}
                </dd>
              </div>
              <div>
                <dt>{t("accountBinding")}</dt>
                <dd>
                  {capital?.accountFingerprint
                    ? t("accountFingerprint", {
                        fingerprint: capital.accountFingerprint,
                      })
                    : t("unavailable")}
                </dd>
              </div>
              <div>
                <dt>{t("configurationBinding")}</dt>
                <dd>
                  {capital?.configurationFingerprint
                    ? t("configFingerprint", {
                        fingerprint: capital.configurationFingerprint,
                      })
                    : t("unavailable")}
                </dd>
              </div>
              <div>
                <dt>{t("executionPolicy")}</dt>
                <dd>
                  {t("riskSizedLimitDay", {
                    notional: formatMoney(capital?.riskPolicy.maxOrderNotional),
                    positions: capital?.riskPolicy.maxOpenPositions ?? "4",
                  })}
                  <span className="capital-policy-detail">
                    {t("dispatchQuoteWindow", {
                      seconds:
                        capital?.riskPolicy.maxDispatchQuoteAgeSeconds ?? "10",
                    })}
                  </span>
                </dd>
              </div>
            </dl>
          </div>

          {recoveryOnly && (
            <Alert className="paper-boundary-alert">
              <TriangleAlert />
              <AlertTitle>{t("paperRecoveryRequired")}</AlertTitle>
              <AlertDescription>
                {t("paperRecoveryRequiredDetail")}
              </AlertDescription>
            </Alert>
          )}

          <Alert className="paper-boundary-alert">
            <ShieldCheck />
            <AlertTitle>{t("paperBoundary")}</AlertTitle>
            <AlertDescription>
              {t("paperCapitalBoundaryDetail")}
            </AlertDescription>
          </Alert>

          <div className="capital-snapshot-heading">
            <div>
              <h3>{t("brokerSnapshot")}</h3>
              <p>{t("refreshCapitalHelp")}</p>
            </div>
            <Button
              variant="outline"
              disabled={
                preview || !online || pending !== null || !capital?.configured
              }
              onClick={() => void refresh()}
            >
              <RefreshCw
                className={cn(pending === "refresh" && "is-spinning")}
                data-icon="inline-start"
              />
              {pending === "refresh"
                ? t("refreshingBroker")
                : t("refreshBrokerSnapshot")}
            </Button>
          </div>

          {!snapshot ? (
            <div className="capital-empty-state">
              <Landmark />
              <h3>{t("noBrokerSnapshot")}</h3>
              <p>{t("noBrokerSnapshotDetail")}</p>
            </div>
          ) : (
            <>
              <div className="capital-assets" aria-label={t("assets")}>
                <CapitalMeasure
                  label={t("netLiquidation")}
                  value={formatMoney(snapshot.assets.netLiquidation)}
                />
                <CapitalMeasure
                  label={t("availableCash")}
                  value={formatMoney(snapshot.assets.cashAvailableForTrade)}
                />
                <CapitalMeasure
                  label={t("buyingPower")}
                  value={formatMoney(snapshot.assets.buyingPower)}
                />
                <CapitalMeasure
                  label={t("grossPosition")}
                  value={formatMoney(snapshot.assets.grossPositionValue)}
                />
                <CapitalMeasure
                  label={t("unrealizedPnl")}
                  value={formatMoney(snapshot.assets.unrealizedPnl)}
                  tone={finite(snapshot.assets.unrealizedPnl)}
                />
                <CapitalMeasure
                  label={t("realizedPnl")}
                  value={formatMoney(snapshot.assets.realizedPnl)}
                  tone={finite(snapshot.assets.realizedPnl)}
                />
              </div>

              <div className="capital-snapshot-meta">
                <span>
                  <Clock3 /> {relative(snapshot.observedAt)}
                </span>
                <span>
                  {t("positionsCountShort", { count: snapshot.positionCount })}
                </span>
                <span>
                  {t("openOrdersCount", { count: snapshot.openOrderCount })}
                </span>
                <span>
                  {t("recentOrdersCount", { count: snapshot.recentOrderCount })}
                </span>
              </div>

              <Tabs defaultValue="positions" className="capital-tabs">
                <TabsList variant="line" aria-label={t("brokerSnapshot")}>
                  <TabsTrigger value="positions">{t("positions")}</TabsTrigger>
                  <TabsTrigger value="orders">{t("orders")}</TabsTrigger>
                  <TabsTrigger value="audit">
                    {t("capitalAuditTrail")}
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="positions">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("symbol")}</TableHead>
                        <TableHead>{t("quantity")}</TableHead>
                        <TableHead>{t("averageCost")}</TableHead>
                        <TableHead>{t("lastPrice")}</TableHead>
                        <TableHead>{t("marketValue")}</TableHead>
                        <TableHead>{t("pnl")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {snapshot.positions.length ? (
                        snapshot.positions.map((position) => {
                          const pnl = finite(position.unrealizedPnl);
                          return (
                            <TableRow
                              key={`${position.symbol}-${position.securityType}`}
                            >
                              <TableCell>
                                <strong>{position.symbol}</strong>
                                <small>
                                  {position.securityType} · {position.currency}
                                </small>
                              </TableCell>
                              <TableCell>
                                {position.quantity ?? t("unavailable")}
                              </TableCell>
                              <TableCell>
                                {formatMoney(position.averageCost)}
                              </TableCell>
                              <TableCell>
                                {formatMoney(position.marketPrice)}
                              </TableCell>
                              <TableCell>
                                {formatMoney(position.marketValue)}
                              </TableCell>
                              <TableCell
                                className={cn(
                                  "capital-pnl",
                                  pnl !== null &&
                                    (pnl > 0
                                      ? "is-positive"
                                      : pnl < 0 && "is-negative"),
                                )}
                              >
                                {formatMoney(position.unrealizedPnl)}
                                {formatPercent(
                                  position.unrealizedPnlPercent,
                                ) && (
                                  <small>
                                    {formatPercent(
                                      position.unrealizedPnlPercent,
                                    )}
                                  </small>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })
                      ) : (
                        <EmptyTableRow
                          columns={6}
                          label={t("noPaperPositions")}
                        />
                      )}
                    </TableBody>
                  </Table>
                </TabsContent>
                <TabsContent value="orders">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("symbol")}</TableHead>
                        <TableHead>{t("side")}</TableHead>
                        <TableHead>{t("orderType")}</TableHead>
                        <TableHead>{t("status")}</TableHead>
                        <TableHead>{t("filled")}</TableHead>
                        <TableHead>{t("limitPrice")}</TableHead>
                        <TableHead>{t("updated")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {snapshot.orders.length ? (
                        snapshot.orders.map((order) => (
                          <TableRow key={order.reference}>
                            <TableCell>
                              <strong>{order.symbol}</strong>
                              <small>
                                {t("protectedReference", {
                                  reference: order.reference.slice(0, 8),
                                })}
                              </small>
                            </TableCell>
                            <TableCell>{domain(order.side)}</TableCell>
                            <TableCell>
                              {domain(order.orderType)} · {order.timeInForce}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">
                                {domain(order.status)}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              {order.filled ?? "0"} /{" "}
                              {order.quantity ?? t("unavailable")}
                            </TableCell>
                            <TableCell>
                              {formatMoney(order.limitPrice)}
                            </TableCell>
                            <TableCell>
                              {order.updatedAt
                                ? clock(order.updatedAt)
                                : t("unavailable")}
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <EmptyTableRow
                          columns={7}
                          label={t("noRecentOrders")}
                        />
                      )}
                    </TableBody>
                  </Table>
                </TabsContent>
                <TabsContent value="audit">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("action")}</TableHead>
                        <TableHead>{t("result")}</TableHead>
                        <TableHead>{t("accountBinding")}</TableHead>
                        <TableHead>{t("updated")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {capital?.audit.length ? (
                        capital.audit.map((event) => (
                          <TableRow key={event.id}>
                            <TableCell>{domain(event.action)}</TableCell>
                            <TableCell>
                              <span
                                className={cn(
                                  "audit-result",
                                  event.result === "succeeded"
                                    ? "is-success"
                                    : "is-failure",
                                )}
                              >
                                {event.result === "succeeded" ? (
                                  <CircleCheck />
                                ) : (
                                  <TriangleAlert />
                                )}
                                {domain(event.result)}
                              </span>
                            </TableCell>
                            <TableCell>
                              {event.accountFingerprint
                                ? t("accountFingerprint", {
                                    fingerprint: event.accountFingerprint,
                                  })
                                : t("unavailable")}
                            </TableCell>
                            <TableCell>{relative(event.knownAt)}</TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <EmptyTableRow
                          columns={4}
                          label={t("noCapitalAudit")}
                        />
                      )}
                    </TableBody>
                  </Table>
                </TabsContent>
              </Tabs>
            </>
          )}

          <AlertDialog
            open={confirming !== null}
            onOpenChange={(open) => !open && !pending && setConfirming(null)}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogMedia>
                  <LockKeyhole />
                </AlertDialogMedia>
                <AlertDialogTitle>{t("confirmRevokeTitle")}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t("confirmRevokeDetail")}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={pending !== null}>
                  {t("cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={pending !== null}
                  onClick={(event) => {
                    event.preventDefault();
                    void revokeAuthorization();
                  }}
                >
                  {t("confirmRevoke")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </section>
      </TabsContent>
      <TabsContent value="connections">
        <BrokerConnections
          offline={!online || preview}
          runtimeActive={runtimeActive}
          onRequest={onBrokerConnection}
        />
      </TabsContent>
    </Tabs>
  );
}

function CapitalMeasure({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: number | null;
}) {
  return (
    <div className="capital-measure">
      <span>{label}</span>
      <strong
        className={cn(
          tone !== undefined &&
            tone !== null &&
            (tone > 0 ? "is-positive" : tone < 0 && "is-negative"),
        )}
      >
        {value}
      </strong>
    </div>
  );
}

function EmptyTableRow({ columns, label }: { columns: number; label: string }) {
  return (
    <TableRow className="capital-table-empty">
      <TableCell colSpan={columns}>{label}</TableCell>
    </TableRow>
  );
}
