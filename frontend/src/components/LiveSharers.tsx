// "N en direct": travellers sharing their position right now, shown in every screen's header.
// One poll for the whole app, refreshed every REFRESH_MS and when the app comes back.
import { Ionicons } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { Alert, AppState, Pressable, StyleSheet, Text } from "react-native";

import { backendConfigured } from "@/src/api/client";
import { getLiveSummary, LiveSummary } from "@/src/api/network";
import { radius, type, useColors } from "@/src/theme";

const REFRESH_MS = 30_000;
let summary: LiveSummary | null = null;
const listeners = new Set<(s: LiveSummary) => void>();
let timer: ReturnType<typeof setInterval> | null = null;

async function refresh() {
  try {
    summary = await getLiveSummary();
    listeners.forEach((l) => l(summary as LiveSummary));
  } catch {}
}

function subscribe(listener: (s: LiveSummary) => void) {
  listeners.add(listener);
  if (!timer && backendConfigured) {
    refresh();
    timer = setInterval(refresh, REFRESH_MS);
  }
  const sub = AppState.addEventListener("change", (state) => state === "active" && refresh());
  return () => {
    listeners.delete(listener);
    sub.remove();
    if (!listeners.size && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

export function LiveSharers() {
  const colors = useColors();
  const [live, setLive] = useState(summary);
  useEffect(() => subscribe(setLive), []);
  if (!live) return null;
  const n = live.sharers;
  const label = `${n} voyageur${n > 1 ? "s" : ""} partage${n > 1 ? "nt" : ""} sa position en direct`;
  const explain = () =>
    Alert.alert(
      n ? `${n} en direct` : "Personne ne partage en ce moment",
      (n
        ? `${n} voyageur${n > 1 ? "s partagent" : " partage"} la position de ${live.vehicles} véhicule${live.vehicles > 1 ? "s" : ""} en ce moment.`
        : "Aucune position partagée pour l’instant.") +
        "\n\nDans un bus, un métro ou un train ? Ouvrez sa ligne et touchez « Je suis dans ce véhicule » : plus on est nombreux, plus c’est précis.",
    );
  return (
    <Pressable
      onPress={explain}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={[styles.pill, { backgroundColor: n ? colors.okSoft : colors.surfaceSecondary }]}
    >
      <Ionicons name="people" size={14} color={n ? colors.ok : colors.onSurfaceSecondary} />
      <Text style={[styles.text, { color: n ? colors.ok : colors.onSurfaceSecondary }]}>{n} en direct</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  text: { fontSize: type.sm, fontWeight: "700", fontVariant: ["tabular-nums"] },
});
