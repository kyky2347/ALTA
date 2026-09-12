import { useEffect, useRef, useState } from "react";
import { Settings2, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Field,
  FieldLabel,
  FieldGroup,
  FieldSet,
  FieldLegend,
} from "@/components/ui/field";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ApiError, getJson } from "@/lib/api";
import {
  MODEL_ROLES,
  modelProblem,
  validModelRoute,
  type AgentModels,
  type AgentModelState,
  type ModelRoute,
} from "@/lib/agent-models";
import { useI18n } from "@/lib/i18n";

export function AgentModelSettings({
  preview,
  online,
  runtimeActive,
  onSave,
}: {
  preview: boolean;
  online: boolean;
  runtimeActive: boolean;
  onSave: (request: {
    revision: string;
    settings: AgentModels;
  }) => Promise<AgentModelState>;
}) {
  const { t, domain } = useI18n();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<AgentModelState | null>(null);
  const [draft, setDraft] = useState<AgentModels | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const saving = useRef(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!open || preview) return;
    const controller = new AbortController();
    request.current = controller;
    getJson<AgentModelState>("/control/agent-models", {
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) {
          setState(value);
          setDraft(structuredClone(value.settings));
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("modelLoadFailed");
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => {
      controller.abort();
    };
  }, [open, preview, attempt]);
  const locked =
    busy || preview || !online || runtimeActive || error === "modelLoadFailed";
  const problem = draft ? modelProblem(draft) : null;
  const dirty =
    state && draft && JSON.stringify(state.settings) !== JSON.stringify(draft);
  const change = (
    group: "roles" | "scouts",
    id: string,
    route: ModelRoute | null,
  ) => {
    if (!draft || locked) return;
    const next = structuredClone(draft);
    if (route) (next[group] as Record<string, ModelRoute>)[id] = route;
    else delete (next[group] as Record<string, ModelRoute>)[id];
    setDraft(next);
    setSaved(false);
    setError(null);
  };
  async function save() {
    if (!state || !draft || locked || problem || saving.current || !dirty)
      return;
    const current = request.current;
    saving.current = true;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const value = await onSave({ revision: state.revision, settings: draft });
      if (current && !current.signal.aborted) {
        setState(value);
        setDraft(structuredClone(value.settings));
        setSaved(true);
      }
    } catch (failure) {
      if (current && !current.signal.aborted)
        setError(
          failure instanceof ApiError ? failure.code : "modelSaveFailed",
        );
    } finally {
      saving.current = false;
      if (current && !current.signal.aborted) setBusy(false);
    }
  }
  const feedback = (code: string) => {
    const messages = {
      model_route_invalid: "modelInvalid",
      debate_models_must_differ: "modelDebateDifferent",
      audit_model_must_differ: "modelAuditDifferent",
      model_settings_conflict: "modelConflict",
      model_runtime_must_be_stopped: "modelStopFirst",
      operation_in_progress: "modelStopFirst",
      modelLoadFailed: "modelLoadFailed",
    } as const;
    const key = Object.hasOwn(messages, code)
      ? messages[code as keyof typeof messages]
      : null;
    return key ? t(key) : t("modelSaveFailed");
  };
  const row = (group: "roles" | "scouts", id: string, label: string) => {
    if (!draft || !state) return null;
    const selected = (draft[group] as Record<string, ModelRoute>)[id];
    const route = selected ?? draft.roles.scout;
    const prefix = `model-${group}-${id}`;
    const invalid = Boolean(selected && !validModelRoute(selected));
    return (
      <FieldSet key={id} className="model-row" disabled={locked}>
        <FieldLegend>{label}</FieldLegend>
        <FieldGroup className="model-route-fields">
          <Field>
            <FieldLabel htmlFor={`${prefix}-provider`}>
              {t("modelProvider")}
            </FieldLabel>
            <select
              id={`${prefix}-provider`}
              value={selected ? route.provider : "inherit"}
              onChange={(event) =>
                change(
                  group,
                  id,
                  event.target.value === "inherit"
                    ? null
                    : {
                        provider: event.target.value,
                        model:
                          event.target.value === route.provider
                            ? route.model
                            : "",
                      },
                )
              }
            >
              {group === "scouts" && (
                <option value="inherit">{t("modelInherit")}</option>
              )}
              {state.providers.map((provider) => (
                <option key={provider} value={provider}>
                  {provider === "grok"
                    ? "xAI / Grok"
                    : provider === "openai"
                      ? "OpenAI"
                      : provider === "kimi"
                        ? "Moonshot / Kimi"
                        : "DeepSeek"}
                </option>
              ))}
            </select>
          </Field>
          <Field data-invalid={invalid}>
            <FieldLabel htmlFor={`${prefix}-id`}>{t("modelId")}</FieldLabel>
            <Input
              id={`${prefix}-id`}
              aria-invalid={invalid}
              value={route.model}
              disabled={locked || !selected}
              maxLength={128}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) =>
                change(group, id, { ...route, model: event.target.value })
              }
            />
          </Field>
        </FieldGroup>
      </FieldSet>
    );
  };
  return (
    <div className="agent-settings-action">
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!saving.current) {
            if (value && !preview) {
              setBusy(true);
              setError(null);
              setSaved(false);
            }
            setOpen(value);
          }
        }}
      >
        <DialogTrigger asChild>
          <Button variant="outline">
            <Settings2 data-icon="inline-start" />
            {t("modelSettings")}
          </Button>
        </DialogTrigger>
        <DialogContent
          className="model-settings-dialog"
          showCloseButton={!busy}
        >
          <DialogHeader>
            <DialogTitle>{t("modelSettings")}</DialogTitle>
            <DialogDescription>{t("modelSettingsDetail")}</DialogDescription>
          </DialogHeader>
          {(preview || runtimeActive || !online) && (
            <Alert>
              <AlertDescription>
                {t(
                  preview
                    ? "modelPreviewLocked"
                    : runtimeActive
                      ? "modelStopFirst"
                      : "modelOffline",
                )}
              </AlertDescription>
            </Alert>
          )}
          {busy && !draft && <p role="status">{t("loading")}</p>}
          {draft && (
            <div className="model-settings-scroll">
              <FieldGroup>
                {MODEL_ROLES.map((id) =>
                  row(
                    "roles",
                    id,
                    t(
                      (
                        {
                          scout: "modelScout",
                          thesis: "modelThesis",
                          disconfirming: "modelChallenge",
                          moderator: "modelModerator",
                          expression: "modelExpression",
                          audit: "modelAudit",
                          position: "modelPosition",
                        } as const
                      )[id],
                    ),
                  ),
                )}
                <h3>{t("modelScoutOverrides")}</h3>
                {state?.scoutIds.map((id) => row("scouts", id, domain(id)))}
              </FieldGroup>
            </div>
          )}
          {(error || problem) && (
            <Alert variant="destructive">
              <AlertDescription>{feedback(error ?? problem!)}</AlertDescription>
            </Alert>
          )}
          {saved && <p role="status">{t("modelSaved")}</p>}
          <p className="model-availability-note">{t("modelAvailability")}</p>
          <div className="model-settings-footer">
            <Button
              variant="outline"
              disabled={busy || preview}
              onClick={() => {
                if (!dirty || window.confirm(t("modelDiscard"))) {
                  setBusy(true);
                  setError(null);
                  setSaved(false);
                  setAttempt((value) => value + 1);
                }
              }}
            >
              {t("modelReload")}
            </Button>
            <Button
              disabled={locked || Boolean(problem) || !dirty}
              onClick={() => void save()}
            >
              {busy && (
                <LoaderCircle
                  data-icon="inline-start"
                  className="animate-spin"
                />
              )}
              {t(busy ? "modelSaving" : "modelSave")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
