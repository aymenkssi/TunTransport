// Native map: the MapLibre page in a WebView, fed with postMessage.
import { useEffect, useRef, useState } from "react";
import { StyleProp, ViewStyle } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";

import { MAP_HTML, MapData } from "@/src/components/map-html";

type Props = {
  data: MapData;
  onSelectStop?: (id: string) => void;
  onSelectVehicle?: (index: number) => void;
  onPressMap?: (lat: number, lon: number) => void;
  style?: StyleProp<ViewStyle>;
};

export function LineMap({ data, onSelectStop, onSelectVehicle, onPressMap, style }: Props) {
  const ref = useRef<WebView>(null);
  const [loaded, setLoaded] = useState(false);

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

  return (
    <WebView
      ref={ref}
      source={{ html: MAP_HTML, baseUrl: "https://localhost" }}
      originWhitelist={["*"]}
      onMessage={onMessage}
      style={style}
      setSupportMultipleWindows={false}
    />
  );
}
