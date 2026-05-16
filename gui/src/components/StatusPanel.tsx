import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useHealthCheck } from "../hooks/useHealthCheck";
import { useTranslation } from "../i18n";

export default function StatusPanel() {
  const { t } = useTranslation();
  const { data: health, error: healthErr, loading: healthLoading } = useHealthCheck();
  const [apiKeySet, setApiKeySet] = useState<boolean | null>(null);

  useEffect(() => {
    invoke<boolean>("check_api_key")
      .then(setApiKeySet)
      .catch(() => setApiKeySet(null));
  }, []);

  return (
    <div className="panel status-panel">
      <div className="panel-header">
        <span>{t("statusPanel.header")}</span>
      </div>
      <div className="panel-content">
        <div className="status-grid">
          {/* Health card */}
          <div className="status-card">
            <div className="status-card-label">{t("statusPanel.gatewayHealth")}</div>
            {healthLoading ? (
              <div className="loading" />
            ) : healthErr ? (
              <div className="error-text">{healthErr}</div>
            ) : health ? (
              <div className={`status-card-value ${health.reachable ? "green" : "red"}`}>
                {health.reachable ? t("statusPanel.ok") : t("statusPanel.unreachable")}
              </div>
            ) : null}
          </div>

          {/* Port 4000 card */}
          <div className="status-card">
            <div className="status-card-label">{t("statusPanel.port4000")}</div>
            {healthLoading ? (
              <div className="loading" />
            ) : healthErr ? (
              <div className="error-text">{healthErr}</div>
            ) : health?.port_listening ? (
              <div className="status-card-value green">
                {t("statusPanel.listening")}
              </div>
            ) : (
              <div className="status-card-value red">{t("statusPanel.notListening")}</div>
            )}
          </div>

          {/* API key card */}
          <div className="status-card">
            <div className="status-card-label">{t("statusPanel.apiKey")}</div>
            {apiKeySet === null ? (
              <div className="loading" />
            ) : apiKeySet ? (
              <div className="status-card-value green">
                {t("statusPanel.set")}
              </div>
            ) : (
              <div className="status-card-value red">
                {t("statusPanel.notSet")}
              </div>
            )}
          </div>

          {/* Gateway URL card */}
          <div className="status-card">
            <div className="status-card-label">{t("statusPanel.gatewayUrl")}</div>
            <div className="status-card-value" style={{ fontSize: 12 }}>
              {t("statusPanel.gatewayUrlValue")}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
