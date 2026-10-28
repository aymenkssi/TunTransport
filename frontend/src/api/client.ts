// HTTP client for the TunTransport backend with an anonymous user session.
// On first use the app registers an anonymous user and keeps its secret token in secure storage;
// calls that need it (trips) send it as a Bearer token.
import { storage } from "@/src/utils/storage";

const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/+$/, "");
const SESSION_KEY = "tt_user_session";

export const backendConfigured = BASE.length > 0;

type Session = { id: string; token: string };
let session: Session | null = null;
let creating: Promise<Session> | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  if (!backendConfigured) throw new ApiError(0, "Backend not configured");
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
    });
  } catch {
    throw new ApiError(0, "Network error");
  }
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

async function loadOrCreateSession(forceNew = false): Promise<Session> {
  if (session && !forceNew) return session;
  if (!forceNew) {
    const raw = await storage.secureGet(SESSION_KEY);
    if (raw) {
      try {
        session = JSON.parse(raw) as Session;
        return session;
      } catch {}
    }
  }
  if (!creating) {
    creating = request<Session>("/users", { method: "POST" })
      .then(async (created) => {
        session = { id: created.id, token: created.token };
        await storage.secureSet(SESSION_KEY, JSON.stringify(session));
        return session;
      })
      .finally(() => {
        creating = null;
      });
  }
  return creating;
}

/** Authenticated call; recreates the anonymous user once if the server no longer knows the token. */
export async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  const s = await loadOrCreateSession();
  try {
    return await request<T>(path, init, s.token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      const fresh = await loadOrCreateSession(true);
      return request<T>(path, init, fresh.token);
    }
    throw e;
  }
}

/** Deletes the anonymous user and all its trips on the server, then forgets the local token. */
export async function deleteMyData(): Promise<void> {
  const s = session ?? (await loadOrCreateSession());
  await request<{ ok: boolean }>("/users/me/delete", { method: "POST" }, s.token).catch((e) => {
    if (!(e instanceof ApiError && e.status === 401)) throw e;
  });
  session = null;
  await storage.secureSet(SESSION_KEY, "");
}
