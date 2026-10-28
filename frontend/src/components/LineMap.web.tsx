// Web map: same MapLibre page in an iframe (react-native-webview has no web support).
// The page is loaded from a blob: URL rather than srcDoc so it keeps the app's origin:
// with srcDoc the origin is "null" and MapLibre's workers never load the tiles.
import { useEffect, useMemo, useRef, useState } from "react";
import { StyleProp, View, ViewStyle } from "react-native";

import { MAP_HTML, MapData } from "@/src/components/map-html";

type Props = { data: MapData; onSelectStop?: (id: string) => void; style?: StyleProp<ViewStyle> };

export function LineMap({ data, onSelectStop, style }: Props) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [loaded, setLoaded] = useState(false);
  const src = useMemo(() => URL.createObjectURL(new Blob([MAP_HTML], { type: "text/html" })), []);

  useEffect(() => () => URL.revokeObjectURL(src), [src]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow) return;
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "ready") setLoaded(true);
        if (msg.type === "stop" && typeof msg.id === "string") onSelectStop?.(msg.id);
      } catch {}
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [onSelectStop]);

  useEffect(() => {
    if (loaded) frame.current?.contentWindow?.postMessage(JSON.stringify(data), "*");
  }, [data, loaded]);

  return (
    <View style={style}>
      <iframe ref={frame} src={src} title="Carte de la ligne" style={{ border: 0, width: "100%", height: "100%" }} />
    </View>
  );
}
