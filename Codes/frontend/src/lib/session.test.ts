import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api", () => ({
  realClient: { demoSession: vi.fn(), login: vi.fn(), health: vi.fn() },
  loadMockClient: vi.fn(),
}));

import { realClient } from "@/api";
import { ApiError } from "@/api/http";
import { useAuth } from "@/store/auth";
import { signInDemo } from "./session";

const JURY = { username: "TestUser", password: "TestUser11" };
const rc = realClient as unknown as { demoSession: ReturnType<typeof vi.fn>; login: ReturnType<typeof vi.fn>; health: ReturnType<typeof vi.fn> };

describe("one-click private demo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.getState().logout();
  });

  it("signs in with a fresh private session", async () => {
    rc.demoSession.mockResolvedValue({ access_token: "tok-demo", user: { username: "demo-ab12", display_name: "Demo visitor", roles: ["patient"], demo: true } });
    expect(await signInDemo(JURY)).toEqual({ ok: true, mock: false });
    expect(useAuth.getState().token).toBe("tok-demo");
    expect(useAuth.getState().user?.demo).toBe(true);
    expect(rc.login).not.toHaveBeenCalled();
  });

  it("falls back to the shared jury account where demo sessions are switched off", async () => {
    rc.demoSession.mockRejectedValue(new ApiError(404, "Demo sessions are disabled"));
    rc.login.mockResolvedValue({ access_token: "tok-jury", user: { username: "TestUser", display_name: "TestUser", roles: ["patient"] } });
    expect(await signInDemo(JURY)).toEqual({ ok: true, mock: false });
    expect(rc.login).toHaveBeenCalledWith("TestUser", "TestUser11");
    expect(useAuth.getState().token).toBe("tok-jury");
  });

  it("reports the rate limit instead of silently sharing the jury account", async () => {
    rc.demoSession.mockRejectedValue(new ApiError(429, "Too many demo sessions", undefined, 1800));
    expect(await signInDemo(JURY)).toEqual({ ok: false, reason: "limited" });
    expect(rc.login).not.toHaveBeenCalled();
    expect(useAuth.getState().token).toBeNull();
  });
});
