import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n";
import type { ControlState, PaperCapitalStatus } from "@/lib/types";
import type { BrokerExecutionRequest } from "@/lib/broker-execution";
import type {
  BrokerConnectionRequest,
  BrokerVerification,
} from "@/lib/broker-connections";
import { BrokerConnections } from "./broker-connections";
import { BrokerExecutionPanel } from "./broker-execution-panel";

/** Two modes, one exact broker destination. Old Paper authority is drain-only. */
export function CapitalConsole({
  capital,
  control,
  preview,
  online,
  onAuthorization,
  onBrokerExecution,
  onBrokerConnection,
}: {
  capital: PaperCapitalStatus | null;
  control: ControlState | null;
  preview: boolean;
  online: boolean;
  onAuthorization: (enabled: boolean) => Promise<void>;
  onBrokerExecution: (request: BrokerExecutionRequest) => Promise<unknown>;
  onBrokerConnection: (
    request: BrokerConnectionRequest,
  ) => Promise<BrokerVerification>;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState("execution");
  const [provider, setProvider] = useState<string | undefined>();
  const [draining, setDraining] = useState(false);
  const [drainFailed, setDrainFailed] = useState(false);
  const offline = !online || preview;
  const runtimeActive = Boolean(
    control?.runtime.ready ||
      control?.runtime.host?.processAlive ||
      control?.runtime.supervisor?.childProcessAlive,
  );
  const legacyActive = Boolean(
    capital?.requestedEnabled ||
      capital?.enabled ||
      capital?.closeOnly ||
      capital?.drainRequired,
  );
  async function drainLegacy() {
    if (draining || offline) return;
    setDraining(true);
    setDrainFailed(false);
    try {
      await onAuthorization(false);
    } catch {
      setDrainFailed(true);
    } finally {
      setDraining(false);
    }
  }
  return (
    <Tabs value={tab} onValueChange={setTab} className="capital-workspace">
      <TabsList aria-label={t("capitalWorkspace")}>
        <TabsTrigger value="execution">{t("executionAndAccount")}</TabsTrigger>
        <TabsTrigger value="connections">
          {t("brokerConnectionsTitle")}
        </TabsTrigger>
      </TabsList>
      {legacyActive && (
        <Alert>
          <AlertDescription>
            <p>{t("brokerLegacyDrainHelp")}</p>
            <Button
              variant="outline"
              disabled={offline || draining || !capital?.requestedEnabled}
              onClick={() => void drainLegacy()}
            >
              {t("brokerRevokeEntries")}
            </Button>
            {drainFailed && <p role="alert">{t("brokerActionUnconfirmed")}</p>}
          </AlertDescription>
        </Alert>
      )}
      <TabsContent value="execution">
        <BrokerExecutionPanel
          offline={offline}
          runtimeActive={runtimeActive}
          legacyActive={legacyActive}
          initialProvider={provider}
          onRequest={onBrokerExecution}
          onConfigure={(value) => {
            setProvider(value);
            setTab("connections");
          }}
        />
      </TabsContent>
      <TabsContent value="connections">
        <BrokerConnections
          offline={offline}
          runtimeActive={runtimeActive}
          initialProvider={provider}
          onRequest={onBrokerConnection}
          onContinue={(value) => {
            setProvider(value);
            setTab("execution");
          }}
        />
      </TabsContent>
    </Tabs>
  );
}
