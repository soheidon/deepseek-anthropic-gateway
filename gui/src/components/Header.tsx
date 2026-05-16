import { useContext } from "react";
import { useTranslation, LanguageContext } from "../i18n";

interface HeaderProps {
  proxyStatus: "running" | "detected" | "unreachable" | "unknown";
  managedRunning: boolean;
  proxyLoading: boolean;
  proxyError: string | null;
  proxyDiag: string | null;
  onStart: () => void;
  onStop: () => void;
  onClearDiag: () => void;
}

export default function Header({
  proxyStatus,
  managedRunning,
  proxyLoading,
  proxyError,
  proxyDiag,
  onStart,
  onStop,
  onClearDiag,
}: HeaderProps) {
  const { t } = useTranslation();
  const { lang, setLang } = useContext(LanguageContext);

  const statusKey =
    proxyStatus === "running" ? "header.gatewayRunning"
    : proxyStatus === "detected" ? "header.gatewayDetected"
    : proxyStatus === "unreachable" ? "header.gatewayUnreachable"
    : "status.unknown";

  return (
    <header className="app-header">
      <h1>{t("header.title")}</h1>
      <span className={`status-badge status-${proxyStatus}`}>
        {t(statusKey)}
      </span>
      <div className="header-proxy-section">
        {managedRunning ? (
          <button
            className="btn"
            onClick={onStop}
            disabled={proxyLoading}
          >
            {t("header.stopGateway")}
          </button>
        ) : (
          <button
            className="btn btn-primary"
            onClick={onStart}
            disabled={proxyLoading}
          >
            {t("header.startGateway")}
          </button>
        )}
        {proxyError && (
          <span className="proxy-error" title={proxyError}>
            {proxyError.length > 120 ? proxyError.slice(0, 120) + "…" : proxyError}
          </span>
        )}
      </div>
      {proxyDiag && (
        <div className="proxy-diag">
          <div className="proxy-diag-header">
            <span>Diagnostics</span>
            <button className="btn btn-small" onClick={onClearDiag}>x</button>
          </div>
          <pre className="proxy-diag-pre">{proxyDiag}</pre>
        </div>
      )}
      <div className="lang-switcher">
        <button
          className={`lang-option ${lang === "ja" ? "lang-active" : ""}`}
          onClick={() => setLang("ja")}
          aria-label="Switch to Japanese"
        >
          日本語
        </button>
        <span className="lang-separator">|</span>
        <button
          className={`lang-option ${lang === "en" ? "lang-active" : ""}`}
          onClick={() => setLang("en")}
          aria-label="Switch to English"
        >
          English
        </button>
      </div>
    </header>
  );
}
