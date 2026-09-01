import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  BrainCircuit,
  Check,
  CircleAlert,
  Clock3,
  Database,
  EyeOff,
  KeyRound,
  LockKeyhole,
  Newspaper,
  Network,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  TimerReset,
  WifiOff,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";
import type {
  CredentialInventory,
  CredentialSlot,
  CredentialVerificationStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const categoryIcons = {
  models: BrainCircuit,
  market_data: Database,
  news: Newspaper,
  research: Search,
} as const;

const categoryOrder: CredentialSlot["category"][] = [
  "models",
  "market_data",
  "news",
  "research",
];

function providerPurpose(slot: string, t: ReturnType<typeof useI18n>["t"]) {
  if (slot === "deepseek") return t("purposeDeepseek");
  if (slot === "xai") return t("purposeXai");
  if (slot === "kimi") return t("purposeKimi");
  if (slot === "massive") return t("purposeMassive");
  if (slot === "finlight") return t("purposeFinlight");
  if (slot === "finnhub") return t("purposeFinnhub");
  if (slot === "brave") return t("purposeBrave");
  if (slot === "jina") return t("purposeJina");
  if (slot === "openalex") return t("purposeOpenalex");
  return "";
}

type Props = {
  inventory: CredentialInventory | null;
  error: string | null;
  runtimeActive: boolean;
  preview: boolean;
  onVerify: (force?: boolean) => Promise<void>;
  onSave: (slot: string, secret: string) => Promise<void>;
};

const attentionStatuses = new Set<CredentialVerificationStatus>([
  "auth_rejected",
  "rate_limited",
  "unavailable",
]);

function VerificationIcon({
  status,
}: {
  status: CredentialVerificationStatus;
}) {
  if (status === "healthy" || status === "not_required") return <Check />;
  if (status === "auth_rejected") return <ShieldAlert />;
  if (status === "rate_limited") return <TimerReset />;
  if (status === "unavailable") return <WifiOff />;
  if (status === "unverified") return <Clock3 />;
  return <KeyRound />;
}

export function CredentialsCenter({
  inventory,
  error,
  runtimeActive,
  preview,
  onVerify,
  onSave,
}: Props) {
  const { domain, relative, systemMessage, t } = useI18n();
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [savedSlot, setSavedSlot] = useState<string | null>(null);
  const selected =
    inventory?.slots.find((slot) => slot.slot === selectedSlot) ??
    inventory?.slots[0] ??
    null;
  const grouped = useMemo(
    () =>
      categoryOrder
        .map((category) => ({
          category,
          slots:
            inventory?.slots.filter((slot) => slot.category === category) ?? [],
        }))
        .filter((group) => group.slots.length),
    [inventory],
  );

  function selectSlot(slot: string) {
    setSelectedSlot(slot);
    setSecret("");
    setActionError(null);
    setSavedSlot(null);
  }

  const verify = useCallback(
    async (force = false) => {
      setRefreshing(true);
      setActionError(null);
      try {
        await onVerify(force);
      } catch (reason) {
        setActionError(
          systemMessage(reason instanceof Error ? reason.message : null) ??
            t("credentialRefreshFailed"),
        );
      } finally {
        setRefreshing(false);
      }
    },
    [onVerify, systemMessage, t],
  );

  useEffect(() => {
    if (preview || !inventory) return;
    const expiresAt = Date.parse(inventory.verification.expiresAt ?? "");
    const delay =
      inventory.verification.checkedAt && Number.isFinite(expiresAt)
        ? Math.max(0, expiresAt - Date.now())
        : 0;
    const timer = window.setTimeout(
      () => void verify(false),
      Math.min(delay, 2_147_483_647),
    );
    return () => window.clearTimeout(timer);
  }, [inventory, preview, verify]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !secret) return;
    setSaving(true);
    setActionError(null);
    try {
      await onSave(selected.slot, secret);
      setSecret("");
      setSavedSlot(selected.slot);
    } catch (reason) {
      setSecret("");
      setActionError(
        systemMessage(reason instanceof Error ? reason.message : null) ??
          t("credentialSaveFailed"),
      );
    } finally {
      setSaving(false);
    }
  }

  const mutationLocked = runtimeActive || preview || !selected?.editable;
  const configured = inventory?.configuredSlots.length ?? 0;
  const verified =
    inventory?.slots.filter((slot) =>
      ["healthy", "not_required"].includes(slot.verification.status),
    ).length ?? 0;
  const attention =
    inventory?.slots.filter((slot) =>
      attentionStatuses.has(slot.verification.status),
    ) ?? [];

  function verificationState(status: CredentialVerificationStatus) {
    if (status === "healthy") return t("apiVerified");
    if (status === "auth_rejected") return t("apiExpiredOrRejected");
    if (status === "rate_limited") return t("apiRateLimited");
    if (status === "unavailable") return t("apiUnavailable");
    if (status === "not_required") return t("availableWithoutKey");
    if (status === "unverified") return t("apiNotVerified");
    return t("credentialMissing");
  }

  function slotState(slot: CredentialSlot) {
    if (
      slot.verification.status === "not_configured" &&
      slot.credentialRequirement === "optional"
    )
      return t("optionalEnhancement");
    return verificationState(slot.verification.status);
  }

  const selectedAttention = selected
    ? attentionStatuses.has(selected.verification.status)
    : false;

  return (
    <section className="credentials-shell">
      <header className="credentials-heading">
        <div>
          <h2>{t("providerCredentials")}</h2>
          <p>{t("credentialCenterDetail")}</p>
        </div>
        <div className="credential-summary" aria-label={t("credentialSummary")}>
          <span>
            <strong>{configured}</strong>
            {t("configured")}
          </span>
          <span>
            <strong>{verified}</strong>
            {t("verified")}
          </span>
          <span>
            <strong>{attention.length}</strong>
            {t("needsAttention")}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={refreshing || preview}
            onClick={() => void verify(true)}
          >
            <RefreshCw
              data-icon="inline-start"
              className={cn(refreshing && "is-spinning")}
            />
            {refreshing ? t("verifyingApis") : t("verifyApis")}
          </Button>
        </div>
      </header>

      {runtimeActive && (
        <Alert className="credential-lock-alert">
          <LockKeyhole />
          <AlertTitle>{t("credentialChangesLocked")}</AlertTitle>
          <AlertDescription>{t("stopBeforeCredentialChange")}</AlertDescription>
        </Alert>
      )}
      {(error || actionError) && (
        <Alert variant="destructive" className="credential-lock-alert">
          <KeyRound />
          <AlertTitle>{t("credentialCenterUnavailable")}</AlertTitle>
          <AlertDescription>
            {systemMessage(actionError ?? error) ??
              t("credentialRefreshFailed")}
          </AlertDescription>
        </Alert>
      )}
      {attention.length > 0 && (
        <Alert variant="destructive" className="credential-lock-alert">
          <CircleAlert />
          <AlertTitle>{t("credentialHealthAttentionTitle")}</AlertTitle>
          <AlertDescription>
            {t("credentialHealthAttentionDetail", {
              providers: attention.map((slot) => slot.label).join(", "),
            })}
          </AlertDescription>
        </Alert>
      )}
      {inventory?.verification.stale &&
        inventory.verification.checkedAt &&
        attention.length === 0 && (
          <Alert className="credential-lock-alert credential-stale-alert">
            <Clock3 />
            <AlertTitle>{t("credentialHealthStaleTitle")}</AlertTitle>
            <AlertDescription>
              {t("credentialHealthStaleDetail")}
            </AlertDescription>
          </Alert>
        )}

      <div className="credentials-workspace">
        <div className="provider-directory">
          {!inventory
            ? Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} className="provider-skeleton" />
              ))
            : grouped.map(({ category, slots }) => {
                const Icon = categoryIcons[category];
                return (
                  <section key={category} className="provider-group">
                    <h3>
                      <Icon /> {domain(category)}
                    </h3>
                    <div>
                      {slots.map((slot) => (
                        <button
                          type="button"
                          key={slot.slot}
                          className={cn(
                            "provider-row",
                            selected?.slot === slot.slot && "is-selected",
                          )}
                          onClick={() => selectSlot(slot.slot)}
                        >
                          <span
                            className={cn(
                              "provider-state",
                              `is-${slot.verification.status}`,
                            )}
                          >
                            <VerificationIcon
                              status={slot.verification.status}
                            />
                          </span>
                          <span>
                            <strong>{slot.label}</strong>
                            <small>{slotState(slot)}</small>
                          </span>
                          {slot.sourceKind === "environment" && (
                            <Badge variant="outline">ENV</Badge>
                          )}
                        </button>
                      ))}
                    </div>
                  </section>
                );
              })}
          <section className="provider-group">
            <h3>
              <ShieldCheck /> {t("trading")}
            </h3>
            <div className="provider-row is-disabled" aria-disabled="true">
              <span
                className={cn(
                  "provider-state",
                  inventory?.trading.configured && "is-configured",
                )}
              >
                {inventory?.trading.configured ? <Check /> : <LockKeyhole />}
              </span>
              <span>
                <strong>{inventory?.trading.provider ?? "Tiger Trade"}</strong>
                <small>
                  {inventory?.trading.configured
                    ? t("paperConfigStoredExecutionDisabled")
                    : t("paperExecutionDisabled")}
                </small>
              </span>
              <Badge variant="outline">PAPER</Badge>
            </div>
          </section>
        </div>

        <div className="credential-editor">
          {selected ? (
            <>
              <header>
                <div className="credential-provider-mark">
                  <KeyRound />
                </div>
                <div>
                  <span>{domain(selected.category)}</span>
                  <h3>{selected.label}</h3>
                  <p>{providerPurpose(selected.slot, t)}</p>
                </div>
                <Badge
                  variant={
                    selectedAttention
                      ? "destructive"
                      : selected.verification.status === "healthy"
                        ? "default"
                        : "outline"
                  }
                >
                  {slotState(selected)}
                </Badge>
              </header>

              <div
                className={cn(
                  "credential-verification",
                  `is-${selected.verification.status}`,
                )}
                role="status"
              >
                <VerificationIcon status={selected.verification.status} />
                <div>
                  <strong>{slotState(selected)}</strong>
                  <p>
                    {selected.verification.checkedAt
                      ? t("credentialVerifiedAt", {
                          time: relative(selected.verification.checkedAt),
                        })
                      : t("credentialNeverVerified")}
                    {selected.verification.latencyMs !== null &&
                      ` · ${selected.verification.latencyMs} ms`}
                    {selected.verification.httpStatus !== null &&
                      ` · HTTP ${selected.verification.httpStatus}`}
                  </p>
                </div>
                {inventory?.verification.stale && (
                  <Badge variant="outline">{t("stale")}</Badge>
                )}
              </div>

              <div className="credential-facts">
                <div>
                  <span>{t("source")}</span>
                  <strong>{domain(selected.sourceKind)}</strong>
                </div>
                <div>
                  <span>{t("safeFingerprint")}</span>
                  <strong>
                    {selected.fingerprint
                      ? `sha256:${selected.fingerprint}`
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>{t("activation")}</span>
                  <strong>
                    {selected.configured
                      ? t("nextRuntimeStart")
                      : selected.availableWithoutCredential
                        ? t("availableNow")
                        : t("notActive")}
                  </strong>
                </div>
              </div>

              <form onSubmit={(event) => void submit(event)}>
                <FieldGroup>
                  <Field data-invalid={Boolean(actionError)}>
                    <FieldLabel htmlFor="provider-secret">
                      {t("newProviderToken")}
                    </FieldLabel>
                    <Input
                      id="provider-secret"
                      type="password"
                      autoComplete="off"
                      data-1p-ignore
                      data-bwignore="true"
                      data-lpignore="true"
                      spellCheck={false}
                      value={secret}
                      disabled={mutationLocked || saving}
                      placeholder={t("pasteTokenPlaceholder")}
                      onChange={(event) => {
                        setSecret(event.target.value);
                        setSavedSlot(null);
                      }}
                    />
                    <FieldDescription>
                      {selected.sourceKind === "environment"
                        ? t("environmentCredentialLocked")
                        : t("writeOnlyCredentialHelp")}
                    </FieldDescription>
                    <FieldError>{actionError}</FieldError>
                  </Field>
                </FieldGroup>
                <div className="credential-actions">
                  <span>
                    <EyeOff /> {t("secretNeverReturned")}
                  </span>
                  <Button
                    type="submit"
                    disabled={mutationLocked || saving || !secret.trim()}
                  >
                    {saving ? t("savingSecurely") : t("saveAndActivate")}
                  </Button>
                </div>
              </form>

              {savedSlot === selected.slot && (
                <div className="credential-saved" role="status">
                  <Check />
                  <span>
                    <strong>{t("credentialSaved")}</strong>
                    {t("credentialSavedDetail")}
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="credential-empty">
              <KeyRound />
              <p>{t("selectProvider")}</p>
            </div>
          )}
        </div>
      </div>

      {Boolean(inventory?.providerNetwork?.length) && (
        <section
          className="provider-network"
          aria-label={t("builtInProviderNetwork")}
        >
          <header>
            <Network />
            <div>
              <strong>{t("builtInProviderNetwork")}</strong>
              <p>{t("builtInProviderNetworkDetail")}</p>
            </div>
          </header>
          <div className="provider-network-groups">
            {inventory?.providerNetwork?.map((group) => (
              <div key={group.category}>
                <span>{domain(group.category)}</span>
                <p>{group.providers.join(" · ")}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <footer className="credential-boundary">
        <ShieldCheck />
        <div>
          <strong>{t("paperBoundaryTitle")}</strong>
          <p>{t("paperBoundaryDetail")}</p>
        </div>
      </footer>
    </section>
  );
}
