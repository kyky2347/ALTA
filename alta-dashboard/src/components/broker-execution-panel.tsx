import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import { getJson, ApiError } from "@/lib/api";
import {
  validBrokerCatalog,
  type BrokerConnection,
} from "@/lib/broker-connections";
import {
  validBrokerRoute,
  executionFailure,
  type BrokerRoute,
  type BrokerExecutionRequest,
} from "@/lib/broker-execution";
import { useI18n } from "@/lib/i18n";
import { BrokerAccountPanel } from "./broker-account-panel";
import "./operator-settings.css";

export function BrokerExecutionPanel({
  offline,
  runtimeActive,
  legacyActive,
  onRequest,
  initialProvider,
  onConfigure,
}: {
  offline: boolean;
  runtimeActive: boolean;
  legacyActive: boolean;
  onRequest: (request: BrokerExecutionRequest) => Promise<unknown>;
  initialProvider?: string;
  onConfigure: (provider?: string) => void;
}) {
  const { t } = useI18n();
  const [route, setRoute] = useState<BrokerRoute | null>(null);
  const [brokers, setBrokers] = useState<BrokerConnection[]>([]);
  const [draft, setDraft] = useState<string | null>(initialProvider ?? null);
  const [draftMode, setDraftMode] = useState<"shadow" | "broker" | null>(
    initialProvider ? "broker" : null,
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ReturnType<
    typeof executionFailure
  > | null>(null);
  const [refresh, setRefresh] = useState(0);
  const pending = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (offline) return;
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true);
    Promise.all([
      getJson<unknown>("/control/broker-connections/route", {
        signal: controller.signal,
        timeoutMs: 95000,
      }),
      getJson<unknown>("/control/broker-connections", {
        signal: controller.signal,
        timeoutMs: 95000,
      }),
    ])
      .then(([destination, catalog]) => {
        if (controller.signal.aborted) return;
        if (!validBrokerRoute(destination) || !validBrokerCatalog(catalog))
          throw new Error("invalid_route");
        setRoute(destination);
        setBrokers(catalog.brokers);
        setError(null);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setRoute(null);
          setError(
            executionFailure(reason instanceof ApiError ? reason.code : ""),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [offline, refresh]);
  const mode = draftMode ?? (route?.provider ? "broker" : "shadow");
  const choice =
    mode === "shadow" ? "shadow" : (draft ?? route?.provider ?? "");
  const selected = brokers.find((b) => b.provider === route?.provider);
  const target = brokers.find((b) => b.provider === choice);
  const locked = offline || busy || loading || !route;
  async function apply() {
    if (
      locked ||
      runtimeActive ||
      legacyActive ||
      pending.current ||
      !route ||
      (mode === "broker" && (!target?.configured || target.profile_error))
    )
      return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await onRequest({
        action: "select",
        provider: choice === "shadow" ? null : choice,
        revision: route.revision,
        profile_revision: target?.revision ?? null,
      });
      if (!validBrokerRoute(result)) throw new Error("invalid_route");
      if (mounted.current) {
        setRoute(result);
        setDraft(null);
        setDraftMode(null);
      }
    } catch (reason) {
      if (mounted.current)
        setError(
          executionFailure(reason instanceof ApiError ? reason.code : ""),
        );
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <section
      className="execution-mode-panel"
      aria-label={t("brokerExecutionTitle")}
    >
      <header>
        <h3>{t("brokerExecutionTitle")}</h3>
        <p>{t("brokerRouteHelp")}</p>
      </header>
      <fieldset
        className="broker-mode-choices"
        disabled={locked || runtimeActive || legacyActive}
      >
        <legend>{t("executionMode")}</legend>
        {(["shadow", "broker"] as const).map((value) => (
          <label key={value} data-selected={mode === value}>
            <input
              type="radio"
              name="broker-execution-mode"
              value={value}
              checked={mode === value}
              onChange={() => setDraftMode(value)}
            />
            <span>
              <strong>
                {t(value === "shadow" ? "brokerModeShadow" : "brokerModeApi")}
              </strong>
              <small>
                {t(
                  value === "shadow"
                    ? "brokerModeShadowHelp"
                    : "brokerModeApiHelp",
                )}
              </small>
            </span>
          </label>
        ))}
      </fieldset>
      {mode === "broker" && (
        <ol className="broker-setup-steps" aria-label={t("brokerSetupSteps")}>
          <li>
            <span>1</span>
            <div>
              <strong>{t("brokerStepConnect")}</strong>
              <p>{t("brokerStepConnectHelp")}</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>{t("brokerStepSelect")}</strong>
              <p>{t("brokerStepSelectHelp")}</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>{t("brokerStepAuthorize")}</strong>
              <p>{t("brokerStepAuthorizeHelp")}</p>
            </div>
          </li>
        </ol>
      )}
      <p role="status">
        {t("executionCurrent")}{" "}
        <strong>
          {legacyActive
            ? t("brokerLegacyPaper")
            : !route
              ? t("unavailable")
              : selected
                ? selected.name
                : t("shadowSimulation")}
        </strong>
        {selected && (
          <>
            {" "}
            · <Badge variant="outline">{route?.environment}</Badge> ·{" "}
            {route?.binding?.slice(-8)}
          </>
        )}
      </p>
      {mode === "broker" && (
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="broker-execution-destination">
              {t("brokerDestination")}
            </FieldLabel>
            <select
              id="broker-execution-destination"
              className="broker-destination-select"
              value={choice}
              disabled={locked || runtimeActive || legacyActive}
              onChange={(e) => setDraft(e.target.value)}
            >
              <option value="" disabled>
                {t("brokerChooseProvider")}
              </option>
              {brokers.map((b) => (
                <option
                  key={b.provider}
                  value={b.provider}
                  disabled={Boolean(b.profile_error)}
                >
                  {b.name} · {b.environment ?? t("brokerProfileNotSet")}
                </option>
              ))}
            </select>
            <FieldDescription>{t("brokerDestinationHelp")}</FieldDescription>
          </Field>
        </FieldGroup>
      )}
      {(runtimeActive || legacyActive) && (
        <Alert>
          <AlertDescription>
            {t(legacyActive ? "brokerLegacyConflict" : "executionStopFirst")}
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{t(error)}</AlertDescription>
        </Alert>
      )}
      <div className="execution-actions">
        {mode === "broker" && (
          <Button
            variant="outline"
            disabled={offline || busy}
            onClick={() => onConfigure(choice || undefined)}
          >
            {t("brokerConfigureConnection")}
          </Button>
        )}
        <Button
          onClick={() => void apply()}
          disabled={
            locked ||
            runtimeActive ||
            legacyActive ||
            (mode === "broker" &&
              (!target?.configured || Boolean(target.profile_error))) ||
            choice === (route?.provider ?? "shadow")
          }
        >
          {busy ? t("loading") : t("brokerSelectDestination")}
        </Button>
        <Button
          variant="outline"
          disabled={offline || busy || loading}
          onClick={() => setRefresh((v) => v + 1)}
        >
          <RefreshCw data-icon="inline-start" />
          {t("refresh")}
        </Button>
      </div>
      {selected && route && (
        <BrokerAccountPanel
          key={`${selected.provider}:${selected.revision}:${route.revision}`}
          broker={selected}
          offline={offline}
          refresh={refresh}
          selected
          onAction={onRequest}
        />
      )}
      {mode === "shadow" && !legacyActive && (
        <p className="execution-explainer">{t("shadowSimulationHelp")}</p>
      )}
    </section>
  );
}
