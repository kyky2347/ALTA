import { useMemo, useState, type FormEvent } from "react";
import {
  BrainCircuit,
  Check,
  Database,
  EyeOff,
  KeyRound,
  LockKeyhole,
  Newspaper,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
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
import type { CredentialInventory, CredentialSlot } from "@/lib/types";
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
  onRefresh: () => Promise<void>;
  onSave: (slot: string, secret: string) => Promise<void>;
};

export function CredentialsCenter({
  inventory,
  error,
  runtimeActive,
  preview,
  onRefresh,
  onSave,
}: Props) {
  const { domain, systemMessage, t } = useI18n();
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

  async function refresh() {
    setRefreshing(true);
    setActionError(null);
    try {
      await onRefresh();
    } catch (reason) {
      setActionError(
        systemMessage(reason instanceof Error ? reason.message : null) ??
          t("credentialRefreshFailed"),
      );
    } finally {
      setRefreshing(false);
    }
  }

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
  const operational =
    inventory?.slots.filter((slot) => slot.operational ?? slot.configured)
      .length ?? 0;

  function slotState(slot: CredentialSlot) {
    if (slot.configured) return t("credentialStored");
    if (slot.availableWithoutCredential) return t("availableWithoutKey");
    if (slot.credentialRequirement === "optional")
      return t("optionalEnhancement");
    return t("credentialMissing");
  }

  return (
    <section className="credentials-shell">
      <header className="credentials-heading">
        <div>
          <span className="eyebrow">{t("secureConfiguration")}</span>
          <h2>{t("providerCredentials")}</h2>
          <p>{t("credentialCenterDetail")}</p>
        </div>
        <div className="credential-summary" aria-label={t("credentialSummary")}>
          <span>
            <strong>{configured}</strong>
            {t("configured")}
          </span>
          <span>
            <strong>{inventory?.slots.length ?? 0}</strong>
            {t("supported")}
          </span>
          <span>
            <strong>{operational}</strong>
            {t("operational")}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={refreshing || preview}
            onClick={() => void refresh()}
          >
            <RefreshCw
              data-icon="inline-start"
              className={cn(refreshing && "is-spinning")}
            />
            {t("refresh")}
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
                              (slot.operational ?? slot.configured) &&
                                "is-configured",
                            )}
                          >
                            {(slot.operational ?? slot.configured) ? (
                              <Check />
                            ) : (
                              <KeyRound />
                            )}
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
                    (selected.operational ?? selected.configured)
                      ? "default"
                      : "outline"
                  }
                >
                  {selected.configured
                    ? t("configured")
                    : selected.availableWithoutCredential
                      ? t("availableNoKey")
                      : selected.credentialRequirement === "optional"
                        ? t("optional")
                        : t("notConfigured")}
                </Badge>
              </header>

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
                <input
                  className="sr-only"
                  name="provider"
                  autoComplete="username"
                  value={selected.label}
                  readOnly
                  tabIndex={-1}
                  aria-hidden="true"
                />
                <FieldGroup>
                  <Field data-invalid={Boolean(actionError)}>
                    <FieldLabel htmlFor="provider-secret">
                      {t("newProviderToken")}
                    </FieldLabel>
                    <Input
                      id="provider-secret"
                      type="password"
                      autoComplete="new-password"
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
