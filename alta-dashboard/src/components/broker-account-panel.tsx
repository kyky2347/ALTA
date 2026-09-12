import { useEffect, useState } from "react";
import { ShieldCheck, Check, Minus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
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
import { getJson } from "@/lib/api";
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
}: {
  broker: BrokerConnection;
  offline: boolean;
  refresh: unknown;
}) {
  const { t, number, clock } = useI18n();
  const [state, setState] = useState<BrokerAccountState | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    if (!broker.configured || broker.profile_error || offline) return;
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true);
    setState(null);
    setFailed(false);
    getJson<unknown>(
      `/control/broker-connections/state?provider=${encodeURIComponent(broker.provider)}`,
      { signal: controller.signal, timeoutMs: 95_000 },
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        if (
          !validBrokerAccountState(value) ||
          value.provider !== broker.provider ||
          value.revision !== broker.revision
        )
          throw new Error("invalid_account_state");
        setState(value);
        setTick(Date.now());
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
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
        <Badge variant="outline">{t("brokerTradingUnavailable")}</Badge>
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
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="outline">
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
              {t("brokerAuthorizationBoundary")}
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
              {t("brokerAuthorizationNotReleased")}
            </AlertDescription>
          </Alert>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">{t("close")}</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
