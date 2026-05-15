import { useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "../i18n";
import type { ClaudeConfigCandidate } from "../types";

const CLAUDE_DESKTOP_CONFIG = JSON.stringify(
  {
    inferenceProvider: "gateway",
    inferenceGatewayBaseUrl: "http://127.0.0.1:4000",
    inferenceGatewayApiKey: "sk-local-gateway",
    inferenceGatewayAuthScheme: "bearer",
    inferenceModels: [
      {
        name: "claude-sonnet-4-5",
        labelOverride: "DeepSeek V4 Pro via Gateway",
      },
      {
        name: "claude-haiku-4-5-20251001",
        labelOverride: "DeepSeek V4 Flash via Gateway",
      },
    ],
  },
  null,
  2
);

export function ClaudeConfigPanelContent() {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [foundConfigs, setFoundConfigs] = useState<ClaudeConfigCandidate[] | null>(null);
  const [searching, setSearching] = useState(true);
  const [showManual, setShowManual] = useState(false);

  // Search for Claude config files on mount
  useEffect(() => {
    invoke<ClaudeConfigCandidate[]>("find_claude_configs")
      .then((results) => { setFoundConfigs(results); setSearching(false); })
      .catch((e) => { console.error(e); setSearching(false); });
  }, []);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(CLAUDE_DESKTOP_CONFIG).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  const openAppDataClaude = () => {
    invoke("open_path", { path: "%APPDATA%\\Claude" }).catch(console.error);
  };

  const openUserProfileClaude = () => {
    invoke("open_path", { path: "%USERPROFILE%\\.claude" }).catch(console.error);
  };

  const openLocalAppDataClaude3p = () => {
    invoke("open_path", { path: "%LOCALAPPDATA%\\Claude-3p\\configLibrary" }).catch(console.error);
  };

  const hasConfigs = foundConfigs && foundConfigs.filter((f) => f.likely_config).length > 0;

  return (
    <>
      {/* Help text */}
      <div className="claude-config-help">
        <p>{t("claudeConfig.helpText")}</p>
      </div>

      {/* Discovery results — the main section, shown first */}
      <div className="claude-config-discovery">
        <h4 className="discovery-title">{t("claudeConfig.discoveryTitle")}</h4>
        {searching ? (
          <div className="loading" />
        ) : hasConfigs ? (
          <ul className="discovery-list">
            {foundConfigs.filter((f) => f.likely_config).map((f) => (
              <li key={f.path} className="discovery-item">
                <span className="discovery-likely" title={t("claudeConfig.likelyConfig")}>
                  ✓
                </span>
                <code className="discovery-path">{f.path}</code>
                <button
                  className="btn btn-small"
                  onClick={() => invoke("open_path", { path: f.path }).catch(console.error)}
                >
                  {t("claudeConfig.openFile")}
                </button>
                <button
                  className="btn btn-small"
                  onClick={() => {
                    const lastSep = Math.max(f.path.lastIndexOf("\\"), f.path.lastIndexOf("/"));
                    const dir = lastSep >= 0 ? f.path.substring(0, lastSep) : f.path;
                    invoke("open_path", { path: dir }).catch(console.error);
                  }}
                >
                  {t("claudeConfig.openFolder")}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">{t("claudeConfig.noFilesFound")}</p>
        )}
      </div>

      {/* Manual browse — collapsible, default closed */}
      <div>
        <button
          className="collapse-header"
          onClick={() => setShowManual(!showManual)}
        >
          <span>{showManual ? "▼" : "▶"}</span>
          {t("claudeConfig.browseManually")}
        </button>
        {showManual && (
          <div style={{ paddingLeft: 16 }}>
            <div className="claude-config-path-row">
              <code>%APPDATA%\Claude\claude_desktop_config.json</code>
              <button className="btn btn-small" onClick={openAppDataClaude}>
                {t("claudeConfig.openFolder")}
              </button>
            </div>
            <div className="claude-config-path-row">
              <code>%USERPROFILE%\.claude\settings.json</code>
              <button className="btn btn-small" onClick={openUserProfileClaude}>
                {t("claudeConfig.openFolder")}
              </button>
            </div>
            <div className="claude-config-path-row">
              <code>%LOCALAPPDATA%\Claude-3p\configLibrary\</code>
              <button className="btn btn-small" onClick={openLocalAppDataClaude3p}>
                {t("claudeConfig.openFolder")}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* JSON block */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
          {t("claudeConfig.header")}
        </span>
        <div className="copy-wrapper">
          <button className="btn btn-success btn-small" onClick={handleCopy}>
            {copied ? t("claudeConfig.copied") : t("claudeConfig.copy")}
          </button>
          {copied && <span className="copied-toast">{t("claudeConfig.copied")}</span>}
        </div>
      </div>
      <pre className="json-block">{CLAUDE_DESKTOP_CONFIG}</pre>
    </>
  );
}

// Legacy default export
export default function ClaudeConfigPanel() {
  return <ClaudeConfigPanelContent />;
}
