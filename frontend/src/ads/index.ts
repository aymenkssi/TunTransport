// Safe AdMob wrapper (same approach as Neon Strike). Native ads only work in a development or
// production build, not in Expo Go or on the web: there, everything is a no-op.
import Constants, { ExecutionEnvironment } from "expo-constants";
import { AppState, Platform } from "react-native";

import { getShare } from "@/src/sharing/session";
import { storage } from "@/src/utils/storage";

export const adsSupported = Platform.OS !== "web" && Constants.executionEnvironment !== ExecutionEnvironment.StoreClient;

// Lazily require the native module only when supported.
let mod: any = null;
if (adsSupported) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    mod = require("react-native-google-mobile-ads");
  } catch {
    mod = null;
  }
}

export const AdMob = mod;

// Real ads are served only when EXPO_PUBLIC_AD_MODE=production (set by the EAS "production"
// profile). Every other build uses Google's test IDs: clicking your own live ads can get the
// AdMob account suspended.
const production = process.env.EXPO_PUBLIC_AD_MODE === "production";

// TransTunisLive (Android) ad units — ca-app-pub-7488746561313974. Env vars can override them.
const PROD_AD_UNITS = {
  banner: process.env.EXPO_PUBLIC_BANNER_AD_UNIT || "ca-app-pub-7488746561313974/9387631275",
  interstitial: process.env.EXPO_PUBLIC_INTERSTITIAL_AD_UNIT || "ca-app-pub-7488746561313974/9555152238",
  appOpen: process.env.EXPO_PUBLIC_APP_OPEN_AD_UNIT || "ca-app-pub-7488746561313974/9891840375",
};

export const AD_IDS = {
  banner: production ? PROD_AD_UNITS.banner : mod?.TestIds?.ADAPTIVE_BANNER || mod?.TestIds?.BANNER,
  interstitial: production ? PROD_AD_UNITS.interstitial : mod?.TestIds?.INTERSTITIAL,
  appOpen: production ? PROD_AD_UNITS.appOpen : mod?.TestIds?.APP_OPEN,
};

// ---------------- Consent (GDPR / UMP) ----------------
// Ads may only be requested once Google's consent flow says so (canRequestAds). The consent
// message itself is configured in AdMob > Privacy & messaging.
let canRequestAds = false;
let privacyOptionsRequired = false;
const readyListeners = new Set<() => void>();

export function adsReady() {
  return canRequestAds;
}

// Subscribe to "ads can now be requested" (used by banners mounted before consent resolves).
export function onAdsReady(fn: () => void) {
  readyListeners.add(fn);
  return () => {
    readyListeners.delete(fn);
  };
}

export function isPrivacyOptionsRequired() {
  return privacyOptionsRequired;
}

// Lets the user change their consent later (required by Google when the status is REQUIRED).
export async function showPrivacyOptions() {
  if (!mod?.AdsConsent) return;
  try {
    const info = await mod.AdsConsent.showPrivacyOptionsForm();
    applyConsent(info);
    await startAds();
  } catch {}
}

function applyConsent(info: any) {
  canRequestAds = !!info?.canRequestAds;
  privacyOptionsRequired =
    info?.privacyOptionsRequirementStatus === mod?.AdsConsentPrivacyOptionsRequirementStatus?.REQUIRED;
}

let initStarted = false;

export async function initAds() {
  if (!mod?.default || initStarted) return;
  initStarted = true;
  try {
    // Updates consent info, then shows the consent form only if the user still has to answer it.
    applyConsent(await mod.AdsConsent.gatherConsent());
  } catch {
    // Offline or form unavailable: fall back to the consent collected in a previous session.
    try {
      applyConsent(await mod.AdsConsent.getConsentInfo());
    } catch {}
  }
  await startAds();
}

let sdkStarted = false;

// Starts the Mobile Ads SDK once consent allows it (at launch, or later from the privacy form).
async function startAds() {
  if (!canRequestAds || sdkStarted) return;
  sdkStarted = true;
  try {
    await mod.default().setRequestConfiguration({
      maxAdContentRating: mod.MaxAdContentRating?.PG,
      tagForChildDirectedTreatment: false,
      tagForUnderAgeOfConsent: false,
    });
    await mod.default().initialize();
  } catch {}
  readyListeners.forEach((fn) => fn());
  preloadInterstitial();
  await setupAppOpen();
}

// ---------------- Interstitial ----------------
// Shown only at a natural break: when the user opens a line, once every INTERSTITIAL_EVERY
// times, at most once every INTERSTITIAL_MIN_GAP_MS, and never while they share a trip
// (they are helping everyone, and may be getting on a bus).
export const INTERSTITIAL_EVERY = 4;
const INTERSTITIAL_MIN_GAP_MS = 3 * 60_000;
let interstitial: any = null;
let breaks = 0;
let lastShownAt = 0;

function preloadInterstitial() {
  if (!canRequestAds || !mod?.InterstitialAd || interstitial) return;
  try {
    const ad = mod.InterstitialAd.createForAdRequest(AD_IDS.interstitial);
    const offError = ad.addAdEventListener(mod.AdEventType.ERROR, () => {
      offError();
      if (interstitial === ad) interstitial = null;
    });
    interstitial = ad;
    ad.load();
  } catch {
    interstitial = null;
  }
}

/** Call at a natural break; onDone runs after the ad closes (or right away when no ad is shown). */
export function showInterstitialAtBreak(onDone: () => void, { sharing = false } = {}) {
  if (sharing) {
    onDone();
    return;
  }
  breaks++;
  const due = breaks % INTERSTITIAL_EVERY === 0 && Date.now() - lastShownAt >= INTERSTITIAL_MIN_GAP_MS;
  const ad = interstitial;
  if (!due || !ad?.loaded) {
    if (breaks % INTERSTITIAL_EVERY === 0) breaks--; // not shown: keep it due for the next break
    preloadInterstitial();
    onDone();
    return;
  }
  interstitial = null;
  lastShownAt = Date.now();
  fullScreenUntil = Date.now() + 60 * 60_000; // until closed: its own activity must not trigger an app-open ad
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    fullScreenUntil = Date.now() + 2_000;
    offClosed();
    offError();
    preloadInterstitial();
    onDone();
  };
  const offClosed = ad.addAdEventListener(mod.AdEventType.CLOSED, finish);
  const offError = ad.addAdEventListener(mod.AdEventType.ERROR, finish);
  Promise.resolve()
    .then(() => ad.show())
    .catch(finish);
}

// ---------------- App open ----------------
// Google's format for app launches: shown when the user comes back to the app after a real
// absence (or at launch once the ad is ready), never on the very first launch, never while
// sharing a trip, at most once every APP_OPEN_MIN_GAP_MS.
const APP_OPEN_MIN_GAP_MS = 4 * 60 * 60_000;
const APP_OPEN_MIN_AWAY_MS = 30_000; // permission dialogs and quick app switches do not count
const APP_OPEN_MAX_AGE_MS = 4 * 60 * 60_000; // Google: a loaded app-open ad expires after 4 h
const APP_OPEN_LAUNCH_WINDOW_MS = 6_000; // at launch, only if ready quickly
const LAUNCHES_KEY = "tt_launches";
const APP_OPEN_SHOWN_KEY = "tt_app_open_shown_at";
let appOpen: any = null;
let appOpenLoadedAt = 0;
let appOpenShownAt = 0;
let fullScreenUntil = 0;
let backgroundSince = 0;
let firstLaunch = true;

function loadAppOpen(onLoaded?: () => void) {
  if (!canRequestAds || !mod?.AppOpenAd || !AD_IDS.appOpen) return;
  if (appOpen && Date.now() - appOpenLoadedAt < APP_OPEN_MAX_AGE_MS) return;
  try {
    const ad = mod.AppOpenAd.createForAdRequest(AD_IDS.appOpen);
    const offLoaded = ad.addAdEventListener(mod.AdEventType.LOADED, () => {
      offLoaded();
      appOpenLoadedAt = Date.now();
      onLoaded?.();
    });
    const offError = ad.addAdEventListener(mod.AdEventType.ERROR, () => {
      offError();
      if (appOpen === ad) appOpen = null;
    });
    appOpen = ad;
    appOpenLoadedAt = 0;
    ad.load();
  } catch {
    appOpen = null;
  }
}

function showAppOpen() {
  const ad = appOpen;
  const now = Date.now();
  if (firstLaunch || getShare() || now < fullScreenUntil) return;
  if (now - appOpenShownAt < APP_OPEN_MIN_GAP_MS) return;
  if (!ad?.loaded || now - appOpenLoadedAt > APP_OPEN_MAX_AGE_MS) {
    loadAppOpen();
    return;
  }
  appOpen = null;
  appOpenShownAt = now;
  fullScreenUntil = now + 60 * 60_000;
  storage.set(APP_OPEN_SHOWN_KEY, now);
  const done = () => {
    offClosed();
    offError();
    fullScreenUntil = Date.now() + 2_000;
    loadAppOpen();
  };
  const offClosed = ad.addAdEventListener(mod.AdEventType.CLOSED, done);
  const offError = ad.addAdEventListener(mod.AdEventType.ERROR, done);
  Promise.resolve()
    .then(() => ad.show())
    .catch(done);
}

async function setupAppOpen() {
  if (!mod?.AppOpenAd) return;
  const launches = (await storage.get<number>(LAUNCHES_KEY, 0)) + 1;
  await storage.set(LAUNCHES_KEY, launches);
  firstLaunch = launches <= 1;
  appOpenShownAt = await storage.get<number>(APP_OPEN_SHOWN_KEY, 0);
  const launchedAt = Date.now();
  loadAppOpen(() => {
    if (Date.now() - launchedAt <= APP_OPEN_LAUNCH_WINDOW_MS && AppState.currentState === "active") showAppOpen();
  });
  AppState.addEventListener("change", (state) => {
    if (state === "background") {
      backgroundSince = Date.now();
    } else if (state === "active" && backgroundSince) {
      const away = Date.now() - backgroundSince;
      backgroundSince = 0;
      if (away >= APP_OPEN_MIN_AWAY_MS) showAppOpen();
    }
  });
}
