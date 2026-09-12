import { useEffect, useRef, useState } from "react";
import { Landmark, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ApiError, getJson } from "@/lib/api";
import {
  type BrokerConnection,
  type BrokerConnectionRequest,
  type BrokerVerification,
  validBrokerCatalog,
  brokerCredentialFields,
} from "@/lib/broker-connections";
import { useI18n } from "@/lib/i18n";

export function BrokerConnections({
  offline,
  runtimeActive,
  onRequest,
}: {
  offline: boolean;
  runtimeActive: boolean;
  onRequest: (request: BrokerConnectionRequest) => Promise<BrokerVerification>;
}) {
  const { t, clock } = useI18n();
  const [open, setOpen] = useState(false);
  const [brokers, setBrokers] = useState<BrokerConnection[]>([]);
  const [provider, setProvider] = useState("alpaca");
  const [environment, setEnvironment] = useState<"PAPER" | "LIVE">("PAPER");
  const [account, setAccount] = useState("");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<
    | "brokerInstallRequired"
    | "brokerConnectionUnavailable"
    | "brokerConnectionConflict"
    | null
  >(null);
  const [verification, setVerification] = useState<BrokerVerification | null>(
    null,
  );
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const saving = useRef(false);
  const selected = brokers.find((b) => b.provider === provider);
  const credentialFields = brokerCredentialFields(selected, environment);
  const unavailable = offline || busy || !selected;
  useEffect(() => {
    if (!open || offline) return;
    const controller = new AbortController();
    getJson<unknown>("/control/broker-connections", {
      signal: controller.signal,
    })
      .then((response) => {
        if (!validBrokerCatalog(response)) throw new Error("invalid_catalog");
        if (!controller.signal.aborted) {
          setBrokers(response.brokers);
          const configured = response.brokers.find(
            (b) => b.provider === provider,
          );
          if (configured?.environment) setEnvironment(configured.environment);
          setError(null);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof ApiError &&
              reason.code === "broker_dependencies_not_installed"
              ? "brokerInstallRequired"
              : "brokerConnectionUnavailable",
          );
      });
    return () => controller.abort();
  }, [open, offline, attempt, provider]);
  function clear() {
    setAccount("");
    setCredentials({});
    setVerification(null);
    setError(null);
    setSaved(false);
  }
  async function run(action: "save" | "verify") {
    if (unavailable || saving.current || (action === "save" && runtimeActive))
      return;
    saving.current = true;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const result = await onRequest(
        action === "verify"
          ? { action, provider }
          : {
              action,
              revision: selected.revision,
              profile: {
                provider,
                environment,
                account,
                credentials: Object.fromEntries(
                  credentialFields.map((field) => [field, credentials[field]]),
                ),
              },
            },
      );
      if (action === "verify") setVerification(result);
      else {
        setSaved(true);
        setAccount("");
        setCredentials({});
        setAttempt((v) => v + 1);
      }
    } catch (reason) {
      setVerification(null);
      setError(
        reason instanceof ApiError &&
          /conflict|credential_change|account_profile/.test(reason.code)
          ? "brokerConnectionConflict"
          : "brokerConnectionUnavailable",
      );
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (saving.current) return;
        clear();
        setOpen(next);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" disabled={offline}>
          <Landmark data-icon="inline-start" />
          {t("brokerConnectionsTitle")}
        </Button>
      </DialogTrigger>
      <DialogContent className="broker-credential-dialog">
        <DialogHeader>
          <DialogTitle>{t("brokerConnectionsTitle")}</DialogTitle>
          <DialogDescription>{t("brokerConnectionsHelp")}</DialogDescription>
        </DialogHeader>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{t(error)}</AlertDescription>
          </Alert>
        )}
        {saved && <p role="status">{t("brokerConnectionSaved")}</p>}
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="broker-provider">
              {t("brokerProviderLabel")}
            </FieldLabel>
            <select
              id="broker-provider"
              value={provider}
              disabled={busy || !brokers.length}
              onChange={(e) => {
                clear();
                setProvider(e.target.value);
                const next = brokers.find((b) => b.provider === e.target.value);
                setEnvironment(
                  next?.environment ?? next?.environments[0] ?? "PAPER",
                );
              }}
            >
              {brokers.map((b) => (
                <option key={b.provider} value={b.provider}>
                  {b.name}
                </option>
              ))}
            </select>
          </Field>
          {selected && (
            <>
              <p className="execution-explainer">
                {t(`brokerAuth_${selected.authentication}`)}
              </p>
              <Badge variant="outline">{t("brokerAcceptancePending")}</Badge>
              <Field>
                <FieldLabel htmlFor="broker-environment">
                  {t("brokerEnvironmentLabel")}
                </FieldLabel>
                <select
                  id="broker-environment"
                  value={environment}
                  disabled={unavailable || runtimeActive || selected.configured}
                  onChange={(e) => {
                    clear();
                    setEnvironment(e.target.value as "PAPER" | "LIVE");
                  }}
                >
                  {selected.environments.map((v) => (
                    <option key={v} value={v}>
                      {t(
                        v === "LIVE"
                          ? "brokerLiveEnvironment"
                          : "brokerPaperEnvironment",
                      )}
                    </option>
                  ))}
                </select>
              </Field>
              <Field>
                <FieldLabel htmlFor="broker-account-id">
                  {t("brokerExactAccount")}
                </FieldLabel>
                <Input
                  id="broker-account-id"
                  type="password"
                  autoComplete="off"
                  value={account}
                  maxLength={128}
                  disabled={unavailable || runtimeActive}
                  onChange={(e) => setAccount(e.target.value)}
                />
              </Field>
              {credentialFields.map((field) => (
                <Field key={field}>
                  <FieldLabel htmlFor={`broker-field-${field}`}>
                    {t(`brokerField_${field}`)}
                  </FieldLabel>
                  <Input
                    id={`broker-field-${field}`}
                    type="password"
                    autoComplete="new-password"
                    spellCheck={false}
                    maxLength={16000}
                    disabled={unavailable || runtimeActive}
                    value={credentials[field] ?? ""}
                    onChange={(e) =>
                      setCredentials((v) => ({ ...v, [field]: e.target.value }))
                    }
                  />
                </Field>
              ))}
            </>
          )}
        </FieldGroup>
        {runtimeActive && (
          <p className="execution-explainer">{t("executionStopFirst")}</p>
        )}
        {verification?.snapshot && (
          <div role="status" className="broker-verification-result">
            <strong>
              {t(
                verification.snapshot.account_verified &&
                  verification.snapshot.environment_verified
                  ? "brokerIdentityConfirmed"
                  : "brokerIdentityUnconfirmed",
              )}
            </strong>
            <span>{clock(verification.snapshot.verified_at)}</span>
            <p>
              {t("brokerVerificationCounts", {
                positions: verification.snapshot.positions.length,
                orders: verification.snapshot.orders.length,
              })}
            </p>
            <p>{t("brokerVerificationNotTrading")}</p>
          </div>
        )}
        <div className="execution-actions">
          <Button
            disabled={
              unavailable ||
              runtimeActive ||
              !account ||
              credentialFields.some((f) => !credentials[f])
            }
            onClick={() => void run("save")}
          >
            {busy ? t("loading") : t("brokerSaveCredentials")}
          </Button>
          <Button
            variant="outline"
            disabled={unavailable || !selected?.configured}
            onClick={() => void run("verify")}
          >
            <RefreshCw data-icon="inline-start" />
            {t("brokerVerifyConnection")}
          </Button>
          {error && (
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setAttempt((v) => v + 1)}
            >
              {t("brokerReloadConnections")}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
