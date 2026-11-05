// Native map: the MapLibre page in a WebView, fed with postMessage.
// If the WebView's renderer crashes (GPU driver, outdated Android System WebView), Android closes
// the whole app unless the crash is handled: the map is reloaded, then replaced by a message.
import { useEffect, useRef, useState } from "react";
import { StyleProp, StyleSheet, Text, View, ViewStyle } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";

import { MAP_HTML, MapData } from "@/src/components/map-html";
import { spacing, type, useColors } from "@/src/theme";

const MAX_RELOADS = 2;

type Props = {
  data: MapData;
  onSelectStop?: (id: string) => void;
  onSelectVehicle?: (index: number) => void;
  onPressMap?: (lat: number, lon: number) => void;
  style?: StyleProp<ViewStyle>;
};

export function LineMap({ data, onSelectStop, onSelectVehicle, onPressMap, style }: Props) {
  const ref = useRef<WebView>(null);
  const colors = useColors();
  const [loaded, setLoaded] = useState(false);
  const [crashes, setCrashes] = useState(0);

  useEffect(() => {
    if (loaded) ref.current?.postMessage(JSON.stringify(data));
  }, [data, loaded]);

  const onMessage = (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === "ready") setLoaded(true);
      if (msg.type === "stop" && typeof msg.id === "string") onSelectStop?.(msg.id);
      if (msg.type === "vehicle" && typeof msg.index === "number") onSelectVehicle?.(msg.index);
      if (msg.type === "map") onPressMap?.(msg.lat, msg.lon);
    } catch {}
  };

  const onCrash = () => {
    setLoaded(false);
    setCrashes((n) => n + 1);
  };

  if (crashes > MAX_RELOADS) {
    return (
      <View style={[style, styles.fallback, { backgroundColor: colors.surfaceSecondary }]}>
        <Text style={[styles.fallbackText, { color: colors.onSurfaceSecondary }]}>
          La carte ne peut pas s’afficher sur ce téléphone. Mettez à jour « Android System WebView » et « Chrome » dans le Play Store, puis rouvrez l’application.
        </Text>
      </View>
    );
  }

  return (
    <WebView
      key={crashes}
      ref={ref}
      onRenderProcessGone={onCrash}
      onContentProcessDidTerminate={onCrash}
      source={{ html: MAP_HTML, baseUrl: "https://localhost" }}
      originWhitelist={["*"]}
      onMessage={onMessage}
      style={style}
      setSupportMultipleWindows={false}
    />
  );
}

const styles = StyleSheet.create({
  fallback: { alignItems: "center", justifyContent: "center", padding: spacing.md },
  fallbackText: { fontSize: type.base, textAlign: "center", lineHeight: 20 },
});
