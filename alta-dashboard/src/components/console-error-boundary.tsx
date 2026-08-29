import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageToggle } from "@/components/language-toggle";
import { useI18n } from "@/lib/i18n";

type State = { failed: boolean };

export class ConsoleErrorBoundary extends Component<
  { children: ReactNode },
  State
> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ALTA operator console render failure", error, info);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return <ConsoleFailure />;
  }
}

function ConsoleFailure() {
  const { t } = useI18n();
  return (
    <div className="full-screen-state">
      <div className="state-language-toggle">
        <LanguageToggle />
      </div>
      <ShieldAlert />
      <h1>{t("dashboardRenderFailed")}</h1>
      <p>{t("dashboardRenderFailedDetail")}</p>
      <Button onClick={() => window.location.reload()}>
        <RotateCw data-icon="inline-start" /> {t("reloadConsole")}
      </Button>
    </div>
  );
}
