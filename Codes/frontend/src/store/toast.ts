import { create } from "zustand";

export type ToastTone = "info" | "success" | "warn" | "error";
export interface Toast {
  id: number;
  text: string;
  tone: ToastTone;
}

interface ToastState {
  toasts: Toast[];
  push: (text: string, tone?: ToastTone, ms?: number) => void;
  dismiss: (id: number) => void;
}

let seq = 1;
export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push: (text, tone = "info", ms = 4200) => {
    const id = seq++;
    set({ toasts: [...get().toasts, { id, text, tone }] });
    window.setTimeout(() => get().dismiss(id), ms);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));

export const toast = (text: string, tone?: ToastTone, ms?: number) => useToasts.getState().push(text, tone, ms);
