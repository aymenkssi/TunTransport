// "Mise à jour disponible": the app compares its version with the one published on Google Play
// (set in the admin, Réseau tab) and offers to open the Play Store. Android does not do it for us:
// the store updates apps in the background, on its own schedule.
import Constants from "expo-constants";
import { Alert, AppState, Linking, Platform } from "react-native";

import { backendConfigured, request } from "@/src/api/client";
import { storage } from "@/src/utils/storage";

const PACKAGE = "com.aymenkssi.tuntransport";
const CHECK_EVERY_MS = 12 * 3600_000;
const LATER_FOR_MS = 3 * 24 * 3600_000; // « Plus tard » : on redemande dans 3 jours
const LATER_KEY = "tt_update_later";

type AppVersion = { latest: string | null; minimum: string | null };

const parse = (v: string) => v.split(".").map((n) => parseInt(n, 10) || 0);
/** True when version a is older than b ("1.0.9" < "1.0.10"). */
export function isOlder(a: string, b: string): boolean {
  const [x, y] = [parse(a), parse(b)];
  for (let i = 0; i < 3; i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) < (y[i] ?? 0);
  return false;
}

function openStore() {
  Linking.openURL(`market://details?id=${PACKAGE}`).catch(() =>
    Linking.openURL(`https://play.google.com/store/apps/details?id=${PACKAGE}`),
  );
}

let lastCheck = 0;
let showing = false;

async function check() {
  const current = Constants.expoConfig?.version;
  if (!current || showing || Date.now() - lastCheck < CHECK_EVERY_MS) return;
  lastCheck = Date.now();
  const published = await request<AppVersion>("/app/version").catch(() => null);
  if (!published?.latest || !isOlder(current, published.latest)) return;
  const required = !!published.minimum && isOlder(current, published.minimum);
  const later = await storage.get<{ version: string; at: number } | null>(LATER_KEY, null);
  if (!required && later?.version === published.latest && Date.now() - later.at < LATER_FOR_MS) return;
  showing = true;
  const done = () => (showing = false);
  Alert.alert(
    "Mise à jour disponible",
    required
      ? `Cette version (${current}) n'est plus prise en charge. Installez la version ${published.latest} pour continuer à utiliser TransTunisLive.`
      : `La version ${published.latest} de TransTunisLive est disponible sur Google Play (vous avez la ${current}).`,
    [
      ...(required
        ? []
        : [{ text: "Plus tard", style: "cancel" as const, onPress: () => { storage.set(LATER_KEY, { version: published.latest, at: Date.now() }); done(); } }]),
      { text: "Mettre à jour", onPress: () => { openStore(); done(); lastCheck = 0; } },
    ],
    { cancelable: !required, onDismiss: done },
  );
}

/** Checks at launch and when the app comes back, at most every 12 hours. */
export function startUpdateChecks() {
  if (Platform.OS !== "android" || !backendConfigured) return;
  check();
  AppState.addEventListener("change", (state) => state === "active" && check());
}
