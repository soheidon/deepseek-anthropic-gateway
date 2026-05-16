import { useState, useMemo } from "react";
import Header from "./components/Header";
import TabBar, { type TabId } from "./components/TabBar";
import StatusPanel from "./components/StatusPanel";
import LogPanel from "./components/LogPanel";
import { ConfigPanelContent } from "./components/ConfigPanel";
import { ClaudeConfigPanelContent } from "./components/ClaudeConfigPanel";
import ApiKeyPanel from "./components/ApiKeyPanel";
import { useHealthCheck } from "./hooks/useHealthCheck";
import { useProxyToggle } from "./hooks/useProxyToggle";
import { LanguageProvider } from "./i18n";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const { managedRunning, loading: proxyLoading, error: proxyError, diag: proxyDiag, successMessage, start, stop, clearDiag } = useProxyToggle();
  const { data: health, error: healthError, loading: healthLoading } = useHealthCheck(managedRunning);

  const proxyStatus = useMemo(() => {
    if (health?.managed_child_running) return "running";
    if (!health) return "unknown";
    if (health.reachable) return "detected";
    return "unreachable";
  }, [health]);

  return (
    <LanguageProvider>
      <div className="app">
        <Header
          proxyStatus={proxyStatus}
          managedRunning={health?.managed_child_running ?? false}
          proxyLoading={proxyLoading}
          proxyError={proxyError}
          proxyDiag={proxyDiag}
          successMessage={successMessage}
          onStart={start}
          onStop={stop}
          onClearDiag={clearDiag}
        />
        <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
        {activeTab === "dashboard" ? (
          <>
            <StatusPanel health={health} healthError={healthError} healthLoading={healthLoading} />
            <LogPanel />
          </>
        ) : activeTab === "gateway" ? (
          <div className="tab-content">
            <ConfigPanelContent />
          </div>
        ) : activeTab === "claude" ? (
          <div className="tab-content">
            <ClaudeConfigPanelContent />
          </div>
        ) : (
          <div className="tab-content">
            <ApiKeyPanel />
          </div>
        )}
      </div>
    </LanguageProvider>
  );
}
