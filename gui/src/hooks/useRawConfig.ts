import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { RawConfigResponse, AsyncState } from "../types";

export function useRawConfig(): AsyncState<RawConfigResponse> {
  const [data, setData] = useState<RawConfigResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    invoke<RawConfigResponse>("read_config_raw")
      .then((result) => setData(result))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, error, loading, refresh };
}
