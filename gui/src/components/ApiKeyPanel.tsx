import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTranslation } from "../i18n";

export default function ApiKeyPanel() {
  const { t } = useTranslation();
  const [keyText, setKeyText] = useState("");
  const [keySet, setKeySet] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    invoke<boolean>("check_api_key")
      .then(setKeySet)
      .catch(() => setKeySet(null));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await invoke("set_env_api_key", { key: keyText });
      const ok = await invoke<boolean>("check_api_key");
      setKeySet(ok);
      setSaving(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setSaving(false);
      console.error(e);
    }
  };

  return (
    <>
      <div className="claude-config-help">
        <p>{t("apiKeyPanel.helpText")}</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
            {t("apiKeyPanel.header")}
          </span>
          {keySet === null ? (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>...</span>
          ) : keySet ? (
            <span style={{ fontSize: 11, color: "var(--accent-green)", fontWeight: 600 }}>
              {t("apiKeyPanel.set")}
            </span>
          ) : (
            <span style={{ fontSize: 11, color: "var(--error)", fontWeight: 600 }}>
              {t("apiKeyPanel.notSet")}
            </span>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            className="api-key-input"
            type="password"
            value={keyText}
            onChange={(e) => setKeyText(e.target.value)}
            placeholder={t("apiKeyPanel.placeholder")}
            style={{ flex: 1, maxWidth: 420 }}
          />
          <button
            className="btn btn-primary btn-small"
            onClick={handleSave}
            disabled={saving || !keyText.trim()}
          >
            {saving ? "..." : t("apiKeyPanel.save")}
          </button>
          {saved && <span className="saved-toast">{t("apiKeyPanel.saved")}</span>}
        </div>
      </div>
    </>
  );
}
