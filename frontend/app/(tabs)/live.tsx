// "En direct" tab: the lines being shared right now, with each live vehicle; tap to open the line.
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { backendConfigured } from "@/src/api/client";
import { getLiveVehicles, LineSummary, LiveVehicle } from "@/src/api/network";
import AdBanner from "@/src/ads/AdBanner";
import { LineBadge } from "@/src/components/LineBadge";
import { ShareBanner } from "@/src/components/ShareBanner";
import { Colors, radius, spacing, type, useColors } from "@/src/theme";
import { formatAge } from "@/src/utils/format";

const REFRESH_MS = 10_000;
const STATUS_LABEL: Record<LiveVehicle["status"], string> = { fiable: "Fiable", probable: "Probable", obsolète: "Obsolète" };

type LiveLine = { line: LineSummary; vehicles: LiveVehicle[] };

export default function LiveScreen() {
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [vehicles, setVehicles] = useState<LiveVehicle[] | null>(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setVehicles(await getLiveVehicles());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  // Refreshed only while the tab is on screen.
  useFocusEffect(
    useCallback(() => {
      if (!backendConfigured) return;
      load();
      const timer = setInterval(load, REFRESH_MS);
      return () => clearInterval(timer);
    }, [load]),
  );

  const lines = useMemo<LiveLine[]>(() => {
    const byLine = new Map<string, LiveLine>();
    for (const v of vehicles ?? []) {
      const entry = byLine.get(v.line_id) ?? {
        line: { id: v.line_id, mode: v.mode, short_name: v.line_label, long_name: v.long_name, color: v.color, operator: "" },
        vehicles: [],
      };
      entry.vehicles.push(v);
      byLine.set(v.line_id, entry);
    }
    for (const entry of byLine.values()) entry.vehicles.sort((a, b) => a.direction - b.direction || a.age_s - b.age_s);
    return [...byLine.values()].sort(
      (a, b) => b.vehicles.length - a.vehicles.length || a.line.short_name.localeCompare(b.line.short_name, "fr", { numeric: true }),
    );
  }, [vehicles]);

  const sharers = (vehicles ?? []).reduce((n, v) => n + v.confirmations, 0);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (!backendConfigured) {
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>Serveur non configuré.</Text>
      </View>
    );
  }
  if (vehicles === null) {
    return (
      <View style={styles.center}>
        {error ? <Text style={styles.empty}>Serveur injoignable. Nouvel essai dans quelques secondes…</Text> : <ActivityIndicator color={colors.brand} />}
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <ShareBanner />
      <FlatList
        data={lines}
        keyExtractor={(item) => item.line.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        ListHeaderComponent={
          lines.length ? (
            <Text style={styles.summary}>
              {lines.length} ligne{lines.length > 1 ? "s" : ""} en direct · {vehicles.length} véhicule{vehicles.length > 1 ? "s" : ""} ·{" "}
              {sharers} voyageur{sharers > 1 ? "s" : ""} qui partage{sharers > 1 ? "nt" : ""}
            </Text>
          ) : null
        }
        ListEmptyComponent={
          <View style={styles.emptyBox}>
            <Ionicons name="radio-outline" size={40} color={colors.onSurfaceSecondary} />
            <Text style={styles.emptyTitle}>Aucune ligne partagée pour le moment</Text>
            <Text style={styles.empty}>
              Dans un bus, un métro ou un train ? Ouvrez sa ligne dans l’onglet Lignes et touchez « Je suis dans ce véhicule » : il apparaîtra ici pour tout le monde.
            </Text>
            <Pressable style={styles.cta} onPress={() => router.push("/lines")}>
              <Text style={styles.ctaText}>Choisir ma ligne</Text>
            </Pressable>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            style={({ pressed }) => [styles.card, pressed && styles.pressed]}
            onPress={() => router.push(`/line/${item.line.id}`)}
            accessibilityLabel={`Ligne ${item.line.short_name}, ${item.vehicles.length} véhicule${item.vehicles.length > 1 ? "s" : ""} en direct`}
          >
            <View style={styles.cardHead}>
              <LineBadge line={item.line} />
              <Text style={styles.name} numberOfLines={1}>{item.line.long_name}</Text>
              <View style={styles.count}>
                <View style={styles.dot} />
                <Text style={styles.countText}>{item.vehicles.length}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceSecondary} />
            </View>
            {item.vehicles.map((v, i) => (
              <View key={i} style={styles.vehicle}>
                <View style={[styles.statusDot, { backgroundColor: v.status === "fiable" ? colors.ok : v.status === "probable" ? colors.info : colors.onSurfaceSecondary }]} />
                <Text style={styles.vehicleText} numberOfLines={2}>
                  <Text style={styles.headsign}>→ {v.headsign}</Text>
                  {"  "}
                  {STATUS_LABEL[v.status]} · {v.confirmations} passager{v.confirmations > 1 ? "s" : ""}
                  {v.speed_mps > 1 ? ` · ${Math.round(v.speed_mps * 3.6)} km/h` : ""} · {formatAge(v.age_s)}
                </Text>
              </View>
            ))}
          </Pressable>
        )}
      />
      <AdBanner />
    </View>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: c.surface },
    list: { padding: spacing.md, gap: spacing.sm + 4, flexGrow: 1 },
    summary: { color: c.onSurfaceSecondary, fontSize: type.sm, marginBottom: 2 },
    card: { borderWidth: 1, borderColor: c.border, borderRadius: radius.md, padding: spacing.md - 2, gap: spacing.sm },
    pressed: { backgroundColor: c.surfaceSecondary },
    cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    name: { flex: 1, color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    count: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: c.okSoft, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
    dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: c.ok },
    countText: { color: c.ok, fontWeight: "700", fontSize: type.sm },
    vehicle: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    statusDot: { width: 9, height: 9, borderRadius: 5 },
    vehicleText: { flex: 1, color: c.onSurfaceSecondary, fontSize: type.sm },
    headsign: { color: c.onSurface, fontWeight: "600" },
    emptyBox: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.xl },
    emptyTitle: { color: c.onSurface, fontSize: type.lg, fontWeight: "700", textAlign: "center" },
    empty: { color: c.onSurfaceSecondary, fontSize: type.base, textAlign: "center", lineHeight: 21 },
    cta: { marginTop: spacing.sm, backgroundColor: c.brand, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm + 4 },
    ctaText: { color: c.onBrand, fontWeight: "700", fontSize: type.base },
  });
