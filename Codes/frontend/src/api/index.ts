import type { ApiClient } from "./types";
import { realClient } from "./realClient";
import { useAuth } from "@/store/auth";

let mockPromise: Promise<ApiClient> | null = null;
/** The mock layer is loaded lazily so it stays isolated in its own chunk. */
export function loadMockClient(): Promise<ApiClient> {
  if (!mockPromise) mockPromise = import("@/mocks/mockClient").then((m) => m.mockClient);
  return mockPromise;
}

function current(): Promise<ApiClient> {
  return useAuth.getState().mock ? loadMockClient() : Promise.resolve(realClient);
}

/**
 * `api` is what every component and hook uses. It routes each call to the real backend or,
 * in offline mock mode, to src/mocks. Components never import the mock layer directly.
 */
export const api: ApiClient = new Proxy({} as ApiClient, {
  get(_t, prop: keyof ApiClient | "then") {
    if (prop === "then") return undefined; // never look like a Promise
    return async (...args: unknown[]) => {
      const client = await current();
      const fn = client[prop] as (...a: unknown[]) => Promise<unknown>;
      return fn(...args);
    };
  },
});

export { realClient };
export * from "./types";
