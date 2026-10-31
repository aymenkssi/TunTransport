// One place for "where am I?": permission, device location switched on, then a fix.
// Turning location on from Google's dialog does not give a position at once, so the fix is retried.
import * as Location from "expo-location";
import { Platform } from "react-native";

export type Here = { lat: number; lon: number };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** True once the device location is on; with `ask`, shows Google's "turn on location" dialog first. */
export async function ensureLocationServices(ask: boolean): Promise<boolean> {
  if (await Location.hasServicesEnabledAsync().catch(() => false)) return true;
  if (!ask || Platform.OS !== "android") return false;
  try {
    await Location.enableNetworkProviderAsync();
  } catch {
    return false; // "Non, merci"
  }
  for (let i = 0; i < 5; i++) {
    if (await Location.hasServicesEnabledAsync().catch(() => false)) return true;
    await sleep(400);
  }
  return false;
}

/** The user's position, or null. Without `ask`, never shows a dialog (used at launch). */
export async function currentPosition(ask: boolean): Promise<Here | null> {
  const permission = ask ? await Location.requestForegroundPermissionsAsync() : await Location.getForegroundPermissionsAsync();
  if (!permission.granted) return null;
  if (!(await ensureLocationServices(ask))) return null;
  for (let attempt = 0; attempt < 3; attempt++) {
    const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced, mayShowUserSettingsDialog: false }).catch(() => null);
    if (pos) return { lat: pos.coords.latitude, lon: pos.coords.longitude };
    await sleep(1500);
  }
  const last = await Location.getLastKnownPositionAsync({ maxAge: 10 * 60_000 }).catch(() => null);
  return last ? { lat: last.coords.latitude, lon: last.coords.longitude } : null;
}
