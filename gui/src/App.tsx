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
  const { data: health } = useHealthCheck();
  const { managedRunning, loading: proxyLoading, error: proxyError, start, stop } = useProxyToggle();

  const proxyStatus = useMemo(() => {
    if (managedRunning) return "running";
    if (!health) return "unknown";
    if (health.status === "ok") return "detected";
    if (health.status === "unreachable") return "unreachable";
    return "unknown";
  }, [health, managedRunning]);

  return (
    <LanguageProvider>
      <div className="app">
        <Header
          proxyStatus={proxyStatus}
          managedRunning={managedRunning}
          proxyLoading={proxyLoading}
          proxyError={proxyError}
          onStart={start}
          onStop={stop}
        />
        <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
        {activeTab === "dashboard" ? (
          <>
            <StatusPanel />
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
