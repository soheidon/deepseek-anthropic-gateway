import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { StartProxyResult } from "../types";

export function useProxyToggle(): {
  managedRunning: boolean;
  loading: boolean;
  error: string | null;
  diag: string | null;
  start: () => void;
  stop: () => void;
  clearDiag: () => void;
} {
  const [managedRunning, setManagedRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diag, setDiag] = useState<string | null>(null);

  // Check status on mount
  useEffect(() => {
    invoke<boolean>("proxy_status")
      .then(setManagedRunning)
      .catch(() => setManagedRunning(false));
  }, []);

  // Poll every 3s while managedRunning
  useEffect(() => {
    if (!managedRunning) return;
    const id = setInterval(() => {
      invoke<boolean>("proxy_status")
        .then((alive) => {
          if (!alive) setManagedRunning(false);
        })
        .catch(() => setManagedRunning(false));
    }, 3000);
    return () => clearInterval(id);
  }, [managedRunning]);

  const start = useCallback(() => {
    setLoading(true);
    setError(null);
    setDiag(null);
    invoke<StartProxyResult>("start_proxy")
      .then((result) => {
        setLoading(false);
        if (result.success) {
          setManagedRunning(true);
          setDiag(result.log);
        } else if (result.log === "already_running") {
          setManagedRunning(true);
        }
      })
      .catch((e: unknown) => {
        setLoading(false);
        setError(String(e));
      });
  }, []);

  const stop = useCallback(() => {
    setLoading(true);
    setError(null);
    setDiag(null);
    invoke<string>("stop_proxy")
      .then(() => {
        setLoading(false);
        setManagedRunning(false);
      })
      .catch((e: unknown) => {
        setLoading(false);
        setError(String(e));
      });
  }, []);

  const clearDiag = useCallback(() => setDiag(null), []);

  return { managedRunning, loading, error, diag, start, stop, clearDiag };
}
