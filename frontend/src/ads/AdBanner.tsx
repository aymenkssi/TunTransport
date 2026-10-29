// Anchored adaptive AdMob banner in native builds; nothing on the web or in Expo Go.
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { AD_IDS, AdMob, adsReady, adsSupported, onAdsReady } from "@/src/ads";
import { useColors } from "@/src/theme";

export default function AdBanner() {
  const colors = useColors();
  // Wait for the consent flow before requesting a banner.
  const [ready, setReady] = useState(adsReady());
  const [failed, setFailed] = useState(false);
  useEffect(() => (ready ? undefined : onAdsReady(() => setReady(true))), [ready]);

  if (!adsSupported || !AdMob?.BannerAd || !ready || failed) return null;
  const { BannerAd, BannerAdSize } = AdMob;
  return (
    <View style={[styles.wrap, { borderTopColor: colors.border, backgroundColor: colors.surface }]}>
      <BannerAd unitId={AD_IDS.banner} size={BannerAdSize.ANCHORED_ADAPTIVE_BANNER} onAdFailedToLoad={() => setFailed(true)} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", borderTopWidth: StyleSheet.hairlineWidth },
});
