// Web stub — the AdMob native SDK cannot run on the web: no-op everything.
export const adsSupported = false;
export const AdMob: any = null;
export const AD_IDS = { banner: undefined as string | undefined, interstitial: undefined as string | undefined };

export async function initAds() {}

export function adsReady() {
  return false;
}
export function onAdsReady(_fn: () => void) {
  return () => {};
}
export function isPrivacyOptionsRequired() {
  return false;
}
export async function showPrivacyOptions() {}
export const INTERSTITIAL_EVERY = 4;
export function showInterstitialAtBreak(onDone: () => void, _options: { sharing?: boolean } = {}) {
  onDone();
}
