import { useEffect, useRef, useState } from "react";
import { ShieldCheck, Check, Minus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { getJson, ApiError } from "@/lib/api";
import {
  executionFailure,
  type BrokerExecutionRequest,
} from "@/lib/broker-execution";
import {
  BROKER_CHECKS,
  validBrokerAccountState,
  type BrokerAccountState,
  type BrokerConnection,
} from "@/lib/broker-connections";
import { useI18n } from "@/lib/i18n";
import { BrokerAccountHoldings } from "./broker-account-holdings";

/** Account evidence is read from the local ledger; only Verify contacts a broker. */
export function BrokerAccountPanel({
  broker,
  offline,
  refresh,
  selected = false,
  onAction,
}: {
  broker: BrokerConnection;
  offline: boolean;
  refresh: unknown;
  selected?: boolean;
  onAction?: (request: BrokerExecutionRequest) => Promise<unknown>;
}) {
  const { t, number, clock } = useI18n();
  const [state, setState] = useState<BrokerAccountState | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(() => Date.now());
  const [open, setOpen] = useState(false);
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<ReturnType<
    typeof executionFailure
  > | null>(null);
  const acting = useRef(false);
  const requestEpoch = useRef(0);
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (!broker.configured || broker.profile_error || offline) return;
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true);
    setState(null);
    setFailed(false);
    let timer: ReturnType<typeof setTimeout>;
    const read = () => {
      if (acting.current) {
        timer = setTimeout(read, 10000);
        return;
      }
      const epoch = requestEpoch.current;
      getJson<unknown>(
        `/control/broker-connections/state?provider=${encodeURIComponent(broker.provider)}`,
        { signal: controller.signal, timeoutMs: 95_000 },
      )
        .then((value) => {
          if (controller.signal.aborted || epoch !== requestEpoch.current)
            return;
          if (
            !validBrokerAccountState(value) ||
            value.provider !== broker.provider ||
            value.revision !== broker.revision
          )
            throw new Error("invalid_account_state");
          setState(value);
          setFailed(false);
          setTick(Date.now());
        })
        .catch(() => {
          if (!controller.signal.aborted && epoch === requestEpoch.current)
            setFailed(true);
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setLoading(false);
            timer = setTimeout(read, 10000);
          }
        });
    };
    read();
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    broker.provider,
    broker.revision,
    broker.configured,
    broker.profile_error,
    offline,
    refresh,
  ]);
  useEffect(() => {
    const timer = window.setInterval(() => setTick(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);
  const snapshot = state?.verification.snapshot;
  const age = snapshot ? tick - Date.parse(snapshot.verified_at) : Infinity;
  const fresh =
    !offline &&
    !loading &&
    !failed &&
    Boolean(state?.verification.fresh) &&
    age >= 0 &&
    age <= 30_000;
  const expected = `ENABLE ${broker.environment} ${broker.binding?.slice(-8)}`;
  async function act(action: "verify" | "authorize" | "revoke" | "reconcile") {
    if (!onAction || offline || busy || acting.current || !selected) return;
    if (
      action === "authorize" &&
      (!fresh || !state?.authorization_review.eligible || phrase !== expected)
    )
      return;
    acting.current = true;
    requestEpoch.current += 1;
    setBusy(true);
    setActionError(null);
    try {
      const result = await onAction(
        action === "verify"
          ? { action, provider: broker.provider }
          : action === "authorize"
            ? {
                action,
                provider: broker.provider,
                revision: broker.revision,
                confirmation: phrase,
              }
            : { action, provider: broker.provider, revision: broker.revision },
      );
      if (
        !validBrokerAccountState(result) ||
        result.provider !== broker.provider ||
        result.revision !== broker.revision
      )
        throw new Error("invalid_state");
      if (alive.current) {
        setState(result);
        setFailed(false);
        setTick(Date.now());
        setPhrase("");
        if (action === "authorize") setOpen(false);
        if (action === "revoke") setRevokeOpen(false);
      }
    } catch (reason) {
      if (alive.current)
        setActionError(
          executionFailure(reason instanceof ApiError ? reason.code : ""),
        );
    } finally {
      acting.current = false;
      if (alive.current) setBusy(false);
    }
  }
  const money = (value: string) =>
    number(Number(value), {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    });
  return (
    <section
      className="broker-account-panel"
      aria-label={t("brokerAccountReviewTitle")}
    >
      <header>
        <h3>{t("brokerAccountReviewTitle")}</h3>
        <Badge variant="outline">
          {t(
            !state || failed || loading || offline
              ? "unavailable"
              : state.authority === "entries"
                ? "brokerAuthorityEntries"
                : state.authority === "close_only"
                  ? "brokerAuthorityCloseOnly"
                  : "brokerAuthorityOff",
          )}
        </Badge>
      </header>
      {loading && !offline && <Skeleton className="h-20 w-full" />}
      {failed && (
        <Alert variant="destructive">
          <AlertDescription>
            {t("brokerAccountStateUnavailable")}
          </AlertDescription>
        </Alert>
      )}
      {snapshot && !loading && (
        <>
          <p>
            {t(fresh ? "brokerSnapshotFresh" : "brokerSnapshotHistorical")} ·{" "}
            {clock(snapshot.verified_at)}
          </p>
          <dl className="broker-account-balances">
            <div>
              <dt>{t("brokerEquity")}</dt>
              <dd>{money(snapshot.equity)}</dd>
            </div>
            <div>
              <dt>{t("brokerCash")}</dt>
              <dd>{money(snapshot.cash)}</dd>
            </div>
            <div>
              <dt>{t("brokerBuyingPower")}</dt>
              <dd>{money(snapshot.buying_power)}</dd>
            </div>
          </dl>
          <p>
            {t("brokerVerificationCounts", {
              positions: snapshot.positions.length,
              orders: snapshot.orders.length,
            })}
          </p>
          <BrokerAccountHoldings snapshot={snapshot} />
        </>
      )}
      {!snapshot && !loading && !failed && (
        <p className="execution-explainer">{t("brokerAccountReviewStart")}</p>
      )}
      {!!state?.orders?.length && (
        <section aria-label={t("brokerOwnedOrders")}>
          <h4>{t("brokerOwnedOrders")}</h4>
          <ul className="broker-owned-orders">
            {state.orders.map((order) => (
              <li key={order.client_id}>
                <strong>{order.symbol}</strong>
                <span>
                  {t(
                    order.side === "BUY" ? "brokerOrderBuy" : "brokerOrderSell",
                  )}{" "}
                  · {number(Number(order.filled))} /{" "}
                  {number(Number(order.quantity))}
                </span>
                <Badge variant="outline">
                  {t(
                    order.state === "prepared"
                      ? "brokerOrderState_unknown"
                      : `brokerOrderState_${order.state}`,
                  )}
                </Badge>
                <small>{order.client_id}</small>
              </li>
            ))}
          </ul>
        </section>
      )}
      {actionError && (
        <Alert variant="destructive">
          <AlertDescription>{t(actionError)}</AlertDescription>
        </Alert>
      )}
      {selected && onAction && (
        <div className="execution-actions">
          <Button
            variant="outline"
            disabled={offline || busy || loading}
            onClick={() => void act("verify")}
          >
            {busy ? t("loading") : t("brokerRefreshAccount")}
          </Button>
          <Dialog
            open={revokeOpen}
            onOpenChange={(value) => !busy && setRevokeOpen(value)}
          >
            <DialogTrigger asChild>
              <Button
                variant="outline"
                disabled={
                  offline ||
                  busy ||
                  loading ||
                  !state ||
                  state.authority === "off"
                }
              >
                {t("brokerRevokeEntries")}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>
                  {t("brokerRevokeEntries")} · {broker.name}
                </DialogTitle>
                <DialogDescription>
                  {t("brokerRevokeExplanation")}
                </DialogDescription>
              </DialogHeader>
              {actionError && (
                <Alert variant="destructive">
                  <AlertDescription>{t(actionError)}</AlertDescription>
                </Alert>
              )}
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline" disabled={busy}>
                    {t("cancel")}
                  </Button>
                </DialogClose>
                <Button
                  disabled={busy || offline}
                  onClick={() => void act("revoke")}
                >
                  {busy ? t("loading") : t("brokerRevokeEntries")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Button
            variant="outline"
            disabled={offline || busy || loading || !state}
            onClick={() => void act("reconcile")}
          >
            {t("brokerReconcileAccount")}
          </Button>
        </div>
      )}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) {
            setOpen(value);
            setPhrase("");
            setActionError(null);
          }
        }}
      >
        <DialogTrigger asChild>
          <Button variant="outline" disabled={busy}>
            <ShieldCheck data-icon="inline-start" />
            {t("brokerReviewAuthorization")}
          </Button>
        </DialogTrigger>
        <DialogContent className="broker-authorization-dialog">
          <DialogHeader>
            <DialogTitle>
              {t("brokerReviewAuthorization")} · {broker.name}
            </DialogTitle>
            <DialogDescription>
              {t("brokerAuthorizationScope")}
            </DialogDescription>
          </DialogHeader>
          <p>
            {t(
              !broker.configured
                ? "brokerProfileNotSet"
                : broker.environment === "LIVE"
                  ? "brokerLiveEnvironment"
                  : "brokerPaperEnvironment",
            )}
            {broker.binding && <> · {broker.binding.slice(-8)}</>}
          </p>
          <ul className="broker-authorization-checks">
            {BROKER_CHECKS.map((check) => {
              const passed =
                fresh && state?.authorization_review.checks[check] === true;
              return (
                <li key={check}>
                  {passed ? (
                    <Check aria-hidden="true" />
                  ) : (
                    <Minus aria-hidden="true" />
                  )}
                  <span>{t(`brokerCheck_${check}`)}</span>
                  <Badge variant={passed ? "secondary" : "outline"}>
                    {t(passed ? "brokerCheckPassed" : "brokerCheckPending")}
                  </Badge>
                </li>
              );
            })}
          </ul>
          {state && (
            <p className="execution-explainer">
              {t("brokerConfiguredLimits", {
                order: money(
                  state.authorization_review.limits.max_order_notional,
                ),
                gross: money(
                  state.authorization_review.limits.max_gross_notional,
                ),
              })}
            </p>
          )}
          <Alert>
            <AlertDescription>
              {t(
                selected
                  ? "brokerAuthorizationScope"
                  : "brokerSelectBeforeAuthorize",
              )}
            </AlertDescription>
          </Alert>
          {selected && onAction && (
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor={`broker-authorize-${broker.provider}`}>
                  {t("executionTypePhrase", { phrase: expected })}
                </FieldLabel>
                <Input
                  id={`broker-authorize-${broker.provider}`}
                  value={phrase}
                  onChange={(e) => setPhrase(e.target.value)}
                  disabled={busy || offline}
                  autoComplete="off"
                  spellCheck={false}
                />
              </Field>
            </FieldGroup>
          )}
          {snapshot?.order_preview_required && (
            <p className="execution-explainer">{t("brokerPreviewRequired")}</p>
          )}
          {actionError && (
            <Alert variant="destructive">
              <AlertDescription>{t(actionError)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            {selected && onAction && (
              <Button
                disabled={
                  offline ||
                  busy ||
                  loading ||
                  !fresh ||
                  !state?.authorization_review.eligible ||
                  phrase !== expected ||
                  state.authority !== "off"
                }
                onClick={() => void act("authorize")}
              >
                {busy ? t("loading") : t("brokerAuthorizeSelected")}
              </Button>
            )}
            <DialogClose asChild>
              <Button variant="outline">{t("close")}</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
