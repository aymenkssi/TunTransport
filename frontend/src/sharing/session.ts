// Trip sharing: the passenger declares a line and direction, the phone sends its recent GPS fixes,
// and the server publishes the vehicle only once the trace matches that line.
// State is persisted so the background location task can resume it after the JS context restarts.
import * as Location from "expo-location";
import { Platform } from "react-native";

import { ApiError } from "@/src/api/client";
import { endTrip, Fix, LineSummary, lineLabel, postPositions, startTrip } from "@/src/api/network";
import { storage } from "@/src/utils/storage";

export const LOCATION_TASK = "tt-share-location";
const STATE_KEY = "tt_share_state";
const SEND_INTERVAL_MS = 5_000;
const TRACE_WINDOW_S = 60;
const MAX_FIXES = 30;
const AUTO_STOP_OFF_ROUTE_MS = 2 * 60_000; // hors de la ligne depuis 2 min : arrêt automatique
const MAX_TRIP_MS = 2 * 3600_000;

export type ShareStatus = "checking" | "on_route" | "rejected" | "offline";

export type ShareState = {
  tripId: string;
  lineId: string;
  lineLabel: string;
  lineColor: string | null;
  direction: number;
  headsign: string;
  startedAt: number;
  lastOnRouteAt: number;
  lastSentAt: number;
  status: ShareStatus;
  reason: string | null;
  speedMps: number | null;
  fixes: Fix[];
};

export type StartResult = "ok" | "denied" | "error";

let state: ShareState | null = null;
let restored = false;
let webWatch: Location.LocationSubscription | null = null;
let queue: Promise<void> = Promise.resolve();
const listeners = new Set<() => void>();

export function getShare(): ShareState | null {
  return state;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

async function save(next: ShareState | null): Promise<void> {
  state = next;
  await storage.set(STATE_KEY, next);
  listeners.forEach((l) => l());
}

/** Reloads a trip still in progress (app restarted while the foreground service kept running). */
export async function restoreShare(): Promise<ShareState | null> {
  if (!restored) {
    restored = true;
    state = state ?? (await storage.get<ShareState | null>(STATE_KEY, null));
    listeners.forEach((l) => l());
  }
  return state;
}

async function startUpdates(): Promise<void> {
  const options: Location.LocationTaskOptions = {
    accuracy: Location.Accuracy.High,
    timeInterval: SEND_INTERVAL_MS,
    distanceInterval: 0,
    pausesUpdatesAutomatically: false,
    activityType: Location.ActivityType.OtherNavigation,
    foregroundService: {
      notificationTitle: "Partage de trajet actif",
      notificationBody: "Votre position aide les autres voyageurs. Ouvrez TransTunisLive pour arrêter.",
      notificationColor: "#E70013",
      killServiceOnDestroy: false,
    },
  };
  if (Platform.OS === "web") {
    webWatch = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.High, timeInterval: SEND_INTERVAL_MS, distanceInterval: 0 },
      (loc) => void handleLocations([loc]),
    );
  } else {
    await Location.startLocationUpdatesAsync(LOCATION_TASK, options);
  }
}

async function stopUpdates(): Promise<void> {
  if (Platform.OS === "web") {
    webWatch?.remove();
    webWatch = null;
    return;
  }
  try {
    if (await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK)) {
      await Location.stopLocationUpdatesAsync(LOCATION_TASK);
    }
  } catch {}
}

export async function startSharing(line: LineSummary, direction: number): Promise<StartResult> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) return "denied";
  if (state) await stopSharing();
  try {
    const trip = await startTrip(line.id, direction);
    const now = Date.now();
    await save({
      tripId: trip.id,
      lineId: line.id,
      lineLabel: lineLabel(line),
      lineColor: line.color,
      direction,
      headsign: trip.headsign,
      startedAt: now,
      lastOnRouteAt: now,
      lastSentAt: 0,
      status: "checking",
      reason: null,
      speedMps: null,
      fixes: [],
    });
    await startUpdates();
    return "ok";
  } catch {
    await stopSharing();
    return "error";
  }
}

export async function stopSharing(): Promise<void> {
  const current = state;
  await stopUpdates();
  await save(null);
  if (current) await endTrip(current.tripId).catch(() => {});
}

/** Called by the background task (or the web watcher) with new GPS fixes; serialized. */
export function handleLocations(locations: Location.LocationObject[]): Promise<void> {
  queue = queue.then(() => process(locations)).catch(() => {});
  return queue;
}

async function process(locations: Location.LocationObject[]): Promise<void> {
  const current = await restoreShare();
  if (!current) {
    await stopUpdates(); // orphan service: nothing to share any more
    return;
  }
  const incoming: Fix[] = locations.map((l) => ({
    t: l.timestamp / 1000,
    lat: l.coords.latitude,
    lon: l.coords.longitude,
    accuracy: l.coords.accuracy ?? 50,
  }));
  const all = [...current.fixes, ...incoming].sort((a, b) => a.t - b.t);
  const latest = all.length ? all[all.length - 1].t : 0;
  const fixes = all.filter((f) => latest - f.t <= TRACE_WINDOW_S).slice(-MAX_FIXES);
  const now = Date.now();
  let next: ShareState = { ...current, fixes };

  if (now - current.lastSentAt >= SEND_INTERVAL_MS && fixes.length > 0) {
    next.lastSentAt = now;
    try {
      const result = await postPositions(current.tripId, fixes);
      next = { ...next, status: result.status, reason: result.reason, speedMps: result.speed_mps };
      if (result.status === "on_route") next.lastOnRouteAt = now;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 410 || e.status === 404)) {
        await stopSharing();
        return;
      }
      next.status = "offline";
    }
  }

  if (now - next.lastOnRouteAt > AUTO_STOP_OFF_ROUTE_MS || now - next.startedAt > MAX_TRIP_MS) {
    await stopSharing();
    return;
  }
  // The trip may have been stopped while the request was in flight.
  if (state?.tripId === current.tripId) await save(next);
}
