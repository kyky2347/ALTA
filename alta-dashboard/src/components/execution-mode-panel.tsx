import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Field,
  FieldLabel,
  FieldGroup,
  FieldDescription,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import type { PaperCapitalStatus } from "@/lib/types";

export type BrokerCredentialRequest = {
  revision: string;
  credentials: { tigerId: string; account: string; privateKey: string };
};
type Props = {
  capital: PaperCapitalStatus | null;
  disabled: boolean;
  onMode: (mode: "shadow" | "broker_paper", revision: string) => Promise<void>;
  onCredentials: (request: BrokerCredentialRequest) => Promise<void>;
};

export function ExecutionModePanel({
  capital,
  disabled,
  onMode,
  onCredentials,
}: Props) {
  const { t } = useI18n();
  const [draftChoice, setChoice] = useState<"shadow" | "broker_paper" | null>(
    null,
  );
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [credentials, setCredentials] = useState({
    tigerId: "",
    account: "",
    privateKey: "",
  });
  const current = capital?.execution;
  const choice = draftChoice ?? current?.requested ?? "shadow";
  const locked = disabled || busy || !current;
  const phrase = choice === "shadow" ? "SHADOW" : "TIGER PAPER";
  const message = (reason: unknown) => {
    const code =
      reason && typeof reason === "object" && "code" in reason
        ? String(reason.code)
        : "";
    if (code === "execution_mode_conflict") return t("executionConflict");
    if (code === "broker_environment_override")
      return t("brokerEnvironmentOverride");
    if (code === "broker_account_change_requires_empty_snapshot")
      return t("brokerAccountChangeBlocked");
    if (code.startsWith("tiger_")) return t("brokerInputInvalid");
    return t("executionUnconfirmed");
  };
  async function apply() {
    if (locked || !current || confirmation !== phrase) return;
    setBusy(true);
    setError(null);
    try {
      await onMode(choice, current.revision);
      setConfirmation("");
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (locked || !current || capital?.requestedEnabled) return;
    setBusy(true);
    setError(null);
    try {
      await onCredentials({ revision: current.revision, credentials });
      setCredentials({ tigerId: "", account: "", privateKey: "" });
      setOpen(false);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="execution-mode-panel" aria-label={t("executionMode")}>
      <header>
        <h3>{t("executionMode")}</h3>
        <p>{t("executionModeHelp")}</p>
      </header>
      <p role="status">
        {t("executionCurrent")}{" "}
        <strong>
          {current?.effective === "shadow"
            ? t("shadowSimulation")
            : current?.effective === "broker_paper"
              ? t("brokerApiMode")
              : current?.effective === "close_only"
                ? t("paperRecoveryOnly")
                : t("executionBlocked")}
        </strong>
      </p>
      <Tabs
        value={choice}
        onValueChange={(v) => {
          setChoice(v as typeof choice);
          setConfirmation("");
          setError(null);
        }}
      >
        <TabsList className="execution-mode-options">
          <TabsTrigger value="shadow">{t("shadowSimulation")}</TabsTrigger>
          <TabsTrigger value="broker_paper">{t("brokerApiMode")}</TabsTrigger>
        </TabsList>
        <TabsContent value="shadow">
          <p className="execution-explainer">{t("shadowSimulationHelp")}</p>
        </TabsContent>
        <TabsContent value="broker_paper">
          <p className="execution-explainer">{t("brokerApiHelp")}</p>
        </TabsContent>
      </Tabs>
      {disabled && (
        <p className="execution-explainer">{t("executionStopFirst")}</p>
      )}
      {error && !open && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="execution-confirm">
            {t("executionTypePhrase", { phrase })}
          </FieldLabel>
          <Input
            id="execution-confirm"
            value={confirmation}
            disabled={locked}
            autoComplete="off"
            onChange={(e) => setConfirmation(e.target.value)}
          />
        </Field>
      </FieldGroup>
      <div className="execution-actions">
        <Button
          onClick={() => void apply()}
          disabled={
            locked ||
            confirmation !== phrase ||
            (choice === "broker_paper" && !capital?.configured) ||
            current?.requested === choice
          }
        >
          {busy ? t("loading") : t("executionApply")}
        </Button>
        <Button
          variant="outline"
          disabled={locked || capital?.requestedEnabled}
          onClick={() => {
            setOpen(true);
            setError(null);
          }}
        >
          <KeyRound data-icon="inline-start" />
          {t("brokerConfigure")}
        </Button>
      </div>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          if (!busy) {
            setOpen(v);
            setCredentials({ tigerId: "", account: "", privateKey: "" });
            setError(null);
          }
        }}
      >
        <DialogContent
          className="broker-credential-dialog"
          showCloseButton={!busy}
        >
          <DialogHeader>
            <DialogTitle>{t("brokerConfigure")}</DialogTitle>
            <DialogDescription>{t("brokerCredentialsHelp")}</DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
            autoComplete="off"
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="broker-tiger-id">Tiger ID</FieldLabel>
                <Input
                  id="broker-tiger-id"
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={24}
                  required
                  disabled={locked}
                  value={credentials.tigerId}
                  onChange={(e) =>
                    setCredentials({ ...credentials, tigerId: e.target.value })
                  }
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="broker-account">
                  {t("brokerPaperAccount")}
                </FieldLabel>
                <Input
                  id="broker-account"
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={17}
                  required
                  disabled={locked}
                  value={credentials.account}
                  onChange={(e) =>
                    setCredentials({ ...credentials, account: e.target.value })
                  }
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="broker-private-key">
                  {t("brokerPrivateKey")}
                </FieldLabel>
                <Input
                  id="broker-private-key"
                  type="password"
                  autoComplete="new-password"
                  maxLength={12000}
                  required
                  disabled={locked}
                  value={credentials.privateKey}
                  onChange={(e) =>
                    setCredentials({
                      ...credentials,
                      privateKey: e.target.value,
                    })
                  }
                />
                <FieldDescription>{t("brokerPrivateKeyHelp")}</FieldDescription>
              </Field>
            </FieldGroup>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button
              type="submit"
              disabled={
                locked ||
                !credentials.tigerId ||
                !credentials.account ||
                !credentials.privateKey
              }
            >
              {busy ? t("loading") : t("brokerSaveCredentials")}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
