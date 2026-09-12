import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { ExternalLink, Landmark, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getJson } from "@/lib/api";
import {
  type BrokerConnection,
  type BrokerConnectionRequest,
  type BrokerVerification,
  validBrokerCatalog,
  brokerCredentialFields,
  brokerFieldKind,
  brokerConnectionError,
} from "@/lib/broker-connections";
import { useI18n } from "@/lib/i18n";
import { BrokerAccountPanel } from "./broker-account-panel";
import "./operator-settings.css";

const FIRMS = [
  "FUTUSECURITIES",
  "FUTUINC",
  "FUTUSG",
  "FUTUAU",
  "FUTUCA",
  "FUTUJP",
];

export function BrokerConnections({
  offline,
  runtimeActive,
  onRequest,
}: {
  offline: boolean;
  runtimeActive: boolean;
  onRequest: (request: BrokerConnectionRequest) => Promise<BrokerVerification>;
}) {
  const { t } = useI18n();
  const [brokers, setBrokers] = useState<BrokerConnection[]>([]);
  const [provider, setProvider] = useState("alpaca");
  const [draftEnvironment, setEnvironment] = useState<"PAPER" | "LIVE" | null>(
    null,
  );
  const [account, setAccount] = useState("");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ReturnType<
    typeof brokerConnectionError
  > | null>(null);
  const [verification, setVerification] = useState<BrokerVerification | null>(
    null,
  );
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const saving = useRef(false);
  const mounted = useRef(false);
  const selected = brokers.find((b) => b.provider === provider);
  const environment =
    selected?.environment ??
    draftEnvironment ??
    selected?.environments[0] ??
    "PAPER";
  const fields = brokerCredentialFields(selected, environment);
  const unavailable =
    offline || loading || busy || !selected || Boolean(selected.profile_error);
  const editLocked = unavailable || runtimeActive;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (offline) return;
    const controller = new AbortController();
    // A reconnect starts a new external read: block editing until its revision
    // is confirmed, including when the previous online session had valid data.
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true);
    // First access may install the locked SDK runtime. Normal console polling
    // never reaches brokers; stale responses never re-enable credential editing.
    getJson<unknown>("/control/broker-connections", {
      signal: controller.signal,
      timeoutMs: 95_000,
    })
      .then((response) => {
        if (!validBrokerCatalog(response)) throw new Error("invalid_catalog");
        if (!controller.signal.aborted) {
          setBrokers(response.brokers);
          setError(null);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setBrokers([]);
          setError(
            brokerConnectionError(
              reason instanceof ApiError ? reason.code : "",
            ),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [offline, attempt]);
  function clear() {
    setAccount("");
    setCredentials({});
    setVerification(null);
    setError(null);
    setSaved(false);
  }
  async function run(action: "save" | "verify") {
    if (
      unavailable ||
      saving.current ||
      !selected ||
      (action === "save" && runtimeActive)
    )
      return;
    saving.current = true;
    setBusy(true);
    setError(null);
    setSaved(false);
    setVerification(null);
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
                account: account.trim(),
                credentials: Object.fromEntries(
                  fields.map((field) => [
                    field,
                    credentials[field]?.trim() ?? "",
                  ]),
                ),
              },
            },
      );
      if (!mounted.current) return;
      if (result.provider !== provider) throw new Error("provider_mismatch");
      if (action === "verify") setVerification(result);
      else {
        setSaved(true);
        setAccount("");
        setCredentials({});
        setLoading(true);
        setAttempt((v) => v + 1);
      }
    } catch (reason) {
      if (mounted.current)
        setError(
          brokerConnectionError(reason instanceof ApiError ? reason.code : ""),
        );
    } finally {
      saving.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <section
      className="broker-connections-panel"
      aria-label={t("brokerConnectionsTitle")}
      aria-busy={loading || busy}
    >
      <header className="broker-connections-heading">
        <div>
          <h2>{t("brokerConnectionsTitle")}</h2>
          <p>{t("brokerConnectionsHelp")}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={offline || busy || loading}
          onClick={() => {
            setLoading(true);
            setAttempt((v) => v + 1);
          }}
        >
          <RefreshCw data-icon="inline-start" />
          {t("brokerReloadConnections")}
        </Button>
      </header>
      {offline && (
        <Alert>
          <AlertDescription>{t("brokerOffline")}</AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{t(error)}</AlertDescription>
        </Alert>
      )}
      {!offline && loading && !brokers.length && (
        <div role="status">
          <p>{t("brokerLoading")}</p>
          <Skeleton className="h-28 w-full" />
        </div>
      )}
      {!!brokers.length && (
        <div className="broker-settings-layout">
          <nav
            className="broker-provider-list"
            aria-label={t("brokerProviderLabel")}
          >
            {brokers.map((b) => (
              <Button
                variant="ghost"
                key={b.provider}
                aria-current={b.provider === provider ? "true" : undefined}
                disabled={busy || loading}
                onClick={() => {
                  if (!saving.current) {
                    clear();
                    setEnvironment(null);
                    setProvider(b.provider);
                  }
                }}
              >
                <Landmark aria-hidden="true" />
                <span>
                  {b.name}
                  <small>
                    {t(
                      b.profile_error
                        ? "brokerProfileUnreadableShort"
                        : b.configured
                          ? "brokerProfileSaved"
                          : "brokerProfileNotSet",
                    )}
                  </small>
                </span>
              </Button>
            ))}
          </nav>
          {selected && (
            <div className="broker-profile" key={provider}>
              <header>
                <h3>{selected.name}</h3>
                <Badge variant="outline">{t("brokerReadOnly")}</Badge>
              </header>
              <p className="execution-explainer">
                {t(`brokerAuth_${selected.authentication}`)}
              </p>
              {selected.profile_error && (
                <Alert variant="destructive">
                  <AlertDescription>
                    {t("brokerProfileUnreadable")}
                  </AlertDescription>
                </Alert>
              )}
              <form
                autoComplete="off"
                onSubmit={(event) => {
                  event.preventDefault();
                  void run("save");
                }}
              >
                <FieldGroup className="broker-field-grid">
                  <Field>
                    <FieldLabel htmlFor="broker-environment">
                      {t("brokerEnvironmentLabel")}
                    </FieldLabel>
                    <select
                      id="broker-environment"
                      value={environment}
                      disabled={editLocked || selected.configured}
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
                    {selected.configured && (
                      <FieldDescription>
                        {t("brokerEnvironmentBound")}
                      </FieldDescription>
                    )}
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="broker-account-id">
                      {t("brokerExactAccount")}
                    </FieldLabel>
                    <Input
                      id="broker-account-id"
                      type="password"
                      autoComplete="new-password"
                      value={account}
                      required
                      maxLength={128}
                      disabled={editLocked}
                      onChange={(e) => setAccount(e.target.value)}
                    />
                    <FieldDescription>
                      {t(
                        selected.provider === "alpaca"
                          ? "brokerAccountUuid"
                          : "brokerAccountBound",
                      )}
                    </FieldDescription>
                  </Field>
                  {fields.map((field) => {
                    const kind = brokerFieldKind(field);
                    const shared = {
                      id: `broker-field-${field}`,
                      autoComplete: "new-password",
                      spellCheck: false,
                      required: true,
                      disabled: editLocked,
                      value: credentials[field] ?? "",
                      onChange: (
                        e: ChangeEvent<
                          | HTMLInputElement
                          | HTMLTextAreaElement
                          | HTMLSelectElement
                        >,
                      ) =>
                        setCredentials((v) => ({
                          ...v,
                          [field]: e.target.value,
                        })),
                    };
                    return (
                      <Field
                        key={field}
                        className={
                          kind === "key" ? "broker-field-wide" : undefined
                        }
                      >
                        <FieldLabel htmlFor={shared.id}>
                          {t(`brokerField_${field}`)}
                        </FieldLabel>
                        {kind === "firm" ? (
                          <select {...shared}>
                            <option value="" disabled>
                              {t("brokerSelectFirm")}
                            </option>
                            {FIRMS.map((firm) => (
                              <option key={firm} value={firm}>
                                {firm}
                              </option>
                            ))}
                          </select>
                        ) : kind === "key" ? (
                          <Textarea
                            {...shared}
                            maxLength={16000}
                            rows={4}
                            className="broker-secret-textarea"
                          />
                        ) : (
                          <Input
                            {...shared}
                            type={kind === "number" ? "text" : "password"}
                            inputMode={
                              kind === "number" ? "numeric" : undefined
                            }
                            pattern={kind === "number" ? "[0-9]+" : undefined}
                            maxLength={kind === "number" ? 10 : 16000}
                          />
                        )}
                      </Field>
                    );
                  })}
                </FieldGroup>
                {runtimeActive && (
                  <p className="execution-explainer">
                    {t("executionStopFirst")}
                  </p>
                )}
                {saved && (
                  <p role="status" className="broker-saved">
                    <ShieldCheck aria-hidden="true" />
                    {t("brokerConnectionSaved")}
                  </p>
                )}
                <div className="execution-actions">
                  <Button
                    type="submit"
                    disabled={
                      editLocked ||
                      !account.trim() ||
                      fields.some((f) => !credentials[f]?.trim())
                    }
                  >
                    {busy ? t("loading") : t("brokerSaveCredentials")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={unavailable || !selected.configured}
                    onClick={() => void run("verify")}
                  >
                    <ShieldCheck data-icon="inline-start" />
                    {t("brokerVerifyConnection")}
                  </Button>
                </div>
                <p className="execution-explainer">
                  {t("brokerWriteOnlyHelp")}
                </p>
              </form>
              <BrokerAccountPanel
                key={`${provider}:${selected.revision}:${attempt}`}
                broker={selected}
                offline={offline}
                refresh={`${busy}:${verification?.snapshot?.verified_at ?? ""}`}
              />
              <a
                className="broker-docs-link"
                href={selected.docs}
                target="_blank"
                rel="noreferrer noopener"
              >
                {t("brokerOfficialDocs")}
                <ExternalLink aria-hidden="true" />
              </a>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
