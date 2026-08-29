import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ConsoleErrorBoundary } from "./components/console-error-boundary.tsx";
import { TooltipProvider } from "./components/ui/tooltip.tsx";
import { LocaleProvider } from "./lib/i18n.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LocaleProvider>
      <TooltipProvider delayDuration={300}>
        <ConsoleErrorBoundary>
          <App />
        </ConsoleErrorBoundary>
      </TooltipProvider>
    </LocaleProvider>
  </StrictMode>,
);
