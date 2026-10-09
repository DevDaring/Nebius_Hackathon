import { loadMockClient, realClient } from "@/api";
import { ApiError, UnreachableError } from "@/api/http";
import { isForcedMock, useAuth } from "@/store/auth";

export type SignInResult = { ok: true; mock: boolean } | { ok: false; reason: "invalid" | "error" | "limited"; message?: string };

async function backendReachable(): Promise<boolean> {
  try {
    await realClient.health();
    return true;
  } catch {
    return false;
  }
}

/**
 * Sign in against the real backend. If the backend cannot be reached at login time, fall back
 * to the offline mock layer (the UI then shows an "offline mock" pill on every page).
 */
export async function signIn(username: string, password: string): Promise<SignInResult> {
  const setSession = useAuth.getState().setSession;
  const viaMock = async (): Promise<SignInResult> => {
    const mock = await loadMockClient();
    try {
      const res = await mock.login(username, password);
      setSession({ token: res.access_token, user: res.user, mock: true });
      return { ok: true, mock: true };
    } catch {
      return { ok: false, reason: "invalid" };
    }
  };

  if (isForcedMock()) return viaMock();

  try {
    const res = await realClient.login(username, password);
    setSession({ token: res.access_token, user: res.user, mock: false });
    return { ok: true, mock: false };
  } catch (e) {
    if (e instanceof UnreachableError) return viaMock();
    if (e instanceof ApiError) {
      if ([400, 401, 403, 422].includes(e.status)) return { ok: false, reason: "invalid" };
      // Route missing or server error: only fall back if the backend is not actually healthy.
      if (!(await backendReachable())) return viaMock();
      return { ok: false, reason: "error", message: e.message };
    }
    return { ok: false, reason: "error", message: (e as Error).message };
  }
}

/**
 * One click into a private demo: the backend creates a throw-away user, so visitors never share
 * replay clocks, readings or meals. Where demo sessions are switched off (404) it signs in with the
 * shared jury account instead; offline it uses the mock layer like `signIn`.
 */
export async function signInDemo(jury: { username: string; password: string }): Promise<SignInResult> {
  const setSession = useAuth.getState().setSession;
  const viaMock = async (): Promise<SignInResult> => {
    const mock = await loadMockClient();
    const res = await mock.demoSession();
    setSession({ token: res.access_token, user: res.user, mock: true });
    return { ok: true, mock: true };
  };
  if (isForcedMock()) return viaMock();
  try {
    const res = await realClient.demoSession();
    setSession({ token: res.access_token, user: res.user, mock: false });
    return { ok: true, mock: false };
  } catch (e) {
    if (e instanceof UnreachableError) return viaMock();
    if (e instanceof ApiError) {
      if (e.status === 429) return { ok: false, reason: "limited" };
      if (e.status === 404 || e.status === 405) return signIn(jury.username, jury.password);
      if (!(await backendReachable())) return viaMock();
      return { ok: false, reason: "error", message: e.message };
    }
    return { ok: false, reason: "error", message: (e as Error).message };
  }
}
