import { create } from "zustand";
import type { User } from "@/api/types";
import { readJSON, writeJSON } from "@/lib/storage";

const KEY = "nemotwins.auth";

interface Persisted {
  token: string | null;
  user: User | null;
  /** True when this session runs on the built-in mock layer (VITE_MOCK=1 or backend unreachable at login). */
  mock: boolean;
}

interface AuthState extends Persisted {
  setSession: (s: Persisted) => void;
  logout: () => void;
}

const FORCED_MOCK = import.meta.env.VITE_MOCK === "1";
const initial = readJSON<Persisted>(KEY, { token: null, user: null, mock: FORCED_MOCK });

export const useAuth = create<AuthState>((set) => ({
  token: initial.token,
  user: initial.user,
  mock: FORCED_MOCK || initial.mock,
  setSession: (s) => {
    const next = { ...s, mock: FORCED_MOCK || s.mock };
    writeJSON(KEY, next);
    set(next);
  },
  logout: () => {
    writeJSON(KEY, null);
    set({ token: null, user: null, mock: FORCED_MOCK });
  },
}));

export const isForcedMock = () => FORCED_MOCK;
