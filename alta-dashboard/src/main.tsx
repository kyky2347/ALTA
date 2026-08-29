import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ConsoleErrorBoundary } from "./components/console-error-boundary.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConsoleErrorBoundary>
      <App />
    </ConsoleErrorBoundary>
  </StrictMode>,
);
