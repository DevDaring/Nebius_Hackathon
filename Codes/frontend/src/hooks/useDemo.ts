import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import { usePatients } from "@/api/hooks";
import { useApp } from "@/store/app";
import { toast } from "@/store/toast";

export function useApplyTheme() {
  const theme = useApp((s) => s.theme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);
}

/**
 * One-click deterministic demo reset: POST /api/twin/{pid}/reset for every persona (readings,
 * meals and the replay clock), back to 2 pricks a day and the first persona, then refetch.
 */
export function useResetDemo() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data: patients } = usePatients();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const ids = patients?.map((p) => p.id) ?? [];
      await Promise.all(ids.map((id) => api.resetTwin(id).catch(() => null)));
      useApp.setState({ mealDraft: null, highlight: null, whatIfSeed: null, lastToolCalls: [], stageDinner: null, stageChange: null, safetyAlert: null });
      useApp.getState().setLadder("2");
      if (ids[0]) useApp.getState().setPatient(ids[0]);
      await qc.invalidateQueries();
      toast(t("tour.resetDone"), "success");
    } finally {
      setBusy(false);
    }
  };
  return { run, busy };
}
