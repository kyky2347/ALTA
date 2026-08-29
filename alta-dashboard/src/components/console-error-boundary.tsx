import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

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
    return (
      <div className="full-screen-state">
        <ShieldAlert />
        <h1>The dashboard view could not be rendered</h1>
        <p>
          The research runtime was not changed. Reload the local console to
          rebuild this browser view from durable backend state.
        </p>
        <Button onClick={() => window.location.reload()}>
          <RotateCw data-icon="inline-start" /> Reload console
        </Button>
      </div>
    );
  }
}
