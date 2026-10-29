// Home: live map of every vehicle shared right now on the network, coloured by line.
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { backendConfigured } from "@/src/api/client";
import { getLiveVehicles, LiveVehicle, Mode } from "@/src/api/network";
import { LineBadge } from "@/src/components/LineBadge";
import { LineMap } from "@/src/components/LineMap";
import { MapData } from "@/src/components/map-html";
import { showInterstitialAtBreak } from "@/src/ads";
import { confirmReport } from "@/src/components/report";
import { ShareBanner } from "@/src/components/ShareBanner";
import { getShare } from "@/src/sharing/session";
import { Colors, modeColors, radius, spacing, type, useColors } from "@/src/theme";
import { formatAge } from "@/src/utils/format";

const REFRESH_MS = 10_000;
const MODES: { key: Mode | null; label: string }[] = [
  { key: null, label: "Tout" },
  { key: "metro", label: "Métro" },
  { key: "bus", label: "Bus" },
  { key: "rfr", label: "RFR" },
  { key: "train", label: "Train" },
];
const STATUS_LABEL = { fiable: "Fiable", probable: "Probable", "obsolète": "Obsolète" } as const;

type Me = { lat: number; lon: number };

export default function LiveMapScreen() {
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [vehicles, setVehicles] = useState<LiveVehicle[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [mode, setMode] = useState<Mode | null>(null);
  // A vehicle has no stable id: follow the one of the same line and direction closest to where it was tapped.
  const [selected, setSelected] = useState<{ lineId: string; direction: number; lat: number; lon: number } | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [center, setCenter] = useState<MapData["center"]>(null);

  const refresh = useCallback(() => {
    getLiveVehicles()
      .then((v) => {
        setVehicles(v);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    if (!backendConfigured) return;
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const locate = useCallback(async (ask: boolean) => {
    const permission = ask ? await Location.requestForegroundPermissionsAsync() : await Location.getForegroundPermissionsAsync();
    if (!permission.granted) return;
    const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }).catch(() => null);
    if (!pos) return;
    const here = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    setMe(here);
    setCenter({ key: String(Date.now()), ...here, zoom: 14 });
  }, []);

  // Centre on the user at launch only if location was already allowed: never ask on opening.
  useEffect(() => {
    locate(false);
  }, [locate]);

  const shown = useMemo(() => (vehicles ?? []).filter((v) => !mode || v.mode === mode), [vehicles, mode]);
  const current = useMemo(() => {
    if (!selected) return undefined;
    const candidates = shown.filter((v) => v.line_id === selected.lineId && v.direction === selected.direction);
    const dist = (v: LiveVehicle) => (v.lat - selected.lat) ** 2 + (v.lon - selected.lon) ** 2;
    return candidates.sort((a, b) => dist(a) - dist(b))[0];
  }, [selected, shown]);

  const mapData = useMemo<MapData>(
    () => ({
      fitKey: "network",
      color: colors.brand,
      dashed: false,
      shape: [],
      stops: [],
      vehicles: shown.map((v) => ({
        lat: v.lat,
        lon: v.lon,
        status: v.status,
        confirmations: v.confirmations,
        color: v.color || modeColors[v.mode],
        label: v.line_label.slice(0, 4),
        selected: v === current,
      })),
      me,
      center,
    }),
    [shown, current, me, center, colors.brand],
  );

  const onSelectVehicle = useCallback(
    (index: number) => {
      const v = shown[index];
      if (v) setSelected({ lineId: v.line_id, direction: v.direction, lat: v.lat, lon: v.lon });
    },
    [shown],
  );
  const onPressMap = useCallback(() => setSelected(null), []);

  const count = shown.length;
  const status = !backendConfigured
    ? "Serveur non configuré"
    : offline
      ? "Hors connexion, nouvel essai…"
      : vehicles === null
        ? "Chargement…"
        : count === 0
          ? "Aucun véhicule en direct"
          : `${count} véhicule${count > 1 ? "s" : ""} en direct`;

  return (
    <View style={styles.screen}>
      <LineMap data={mapData} onSelectVehicle={onSelectVehicle} onPressMap={onPressMap} style={StyleSheet.absoluteFill} />

      <View style={styles.top} pointerEvents="box-none">
        <ShareBanner />
        <View style={styles.chips}>
          {MODES.map((m) => (
            <Pressable
              key={m.label}
              onPress={() => setMode(m.key)}
              style={[styles.chip, mode === m.key && styles.chipActive]}
              accessibilityState={{ selected: mode === m.key }}
            >
              <Text style={[styles.chipText, mode === m.key && styles.chipTextActive]}>{m.label}</Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.pill}>
          <View style={[styles.dot, { backgroundColor: count > 0 && !offline ? colors.ok : colors.onSurfaceSecondary }]} />
          <Text style={styles.pillText}>{status}</Text>
        </View>
      </View>

      <Pressable style={styles.locate} onPress={() => locate(true)} accessibilityLabel="Me localiser">
        <Ionicons name="locate" size={22} color={colors.onSurface} />
      </Pressable>

      {current ? (
        <View style={styles.card}>
          <View style={styles.cardRow}>
            <LineBadge
              line={{ id: current.line_id, mode: current.mode, short_name: current.line_label, long_name: current.long_name, color: current.color, operator: "" }}
              large
            />
            <View style={styles.cardText}>
              <Text style={styles.cardTitle} numberOfLines={1}>Vers {current.headsign}</Text>
              <Text style={styles.cardSub} numberOfLines={1}>{current.long_name}</Text>
            </View>
          </View>
          <Text style={styles.cardInfo}>
            {STATUS_LABEL[current.status]} · {current.confirmations} passager{current.confirmations > 1 ? "s" : ""} · {Math.round(current.speed_mps * 3.6)} km/h · {formatAge(current.age_s)}
          </Text>
          <Pressable
            style={styles.cardButton}
            onPress={() => showInterstitialAtBreak(() => router.push(`/line/${current.line_id}`), { sharing: !!getShare() })}
          >
            <Text style={styles.cardButtonText}>Voir la ligne et les arrivées</Text>
            <Ionicons name="chevron-forward" size={16} color={colors.onBrand} />
          </Pressable>
          <Pressable
            style={styles.report}
            onPress={() => confirmReport(current.line_id, current, () => (setSelected(null), refresh()))}
          >
            <Ionicons name="flag-outline" size={14} color={colors.onSurfaceSecondary} />
            <Text style={styles.reportText}>Ce véhicule n’existe pas</Text>
          </Pressable>
        </View>
      ) : vehicles !== null && count === 0 ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Personne ne partage pour le moment</Text>
          <Text style={styles.cardSub}>
            Vous êtes dans un bus, un métro ou un train ? Choisissez votre ligne et touchez « Je suis dans ce véhicule » : les autres voyageurs le verront ici.
          </Text>
          <Pressable style={styles.cardButton} onPress={() => router.push("/lines")}>
            <Text style={styles.cardButtonText}>Choisir ma ligne</Text>
            <Ionicons name="chevron-forward" size={16} color={colors.onBrand} />
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const shadow = { shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 4 };

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    top: { position: "absolute", top: 0, left: 0, right: 0, gap: spacing.sm },
    chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingHorizontal: spacing.md, paddingTop: spacing.sm },
    chip: { paddingHorizontal: spacing.md - 2, paddingVertical: 7, borderRadius: radius.pill, backgroundColor: c.surface, ...shadow },
    chipActive: { backgroundColor: c.onSurface },
    chipText: { color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    chipTextActive: { color: c.surface },
    pill: {
      alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, marginLeft: spacing.md,
      backgroundColor: c.surface, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, ...shadow,
    },
    dot: { width: 8, height: 8, borderRadius: 4 },
    pillText: { color: c.onSurface, fontSize: type.sm, fontWeight: "600" },
    locate: {
      position: "absolute", right: spacing.md, bottom: 200, width: 46, height: 46, borderRadius: 23,
      alignItems: "center", justifyContent: "center", backgroundColor: c.surface, ...shadow,
    },
    card: {
      position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.md,
      backgroundColor: c.surface, borderRadius: radius.lg, padding: spacing.md, gap: spacing.sm, ...shadow,
    },
    cardRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm + 4 },
    cardText: { flex: 1 },
    cardTitle: { color: c.onSurface, fontSize: type.lg, fontWeight: "700" },
    cardSub: { color: c.onSurfaceSecondary, fontSize: type.sm, lineHeight: 18 },
    cardInfo: { color: c.onSurface, fontSize: type.base },
    cardButton: {
      flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
      backgroundColor: c.brand, borderRadius: radius.md, paddingVertical: spacing.sm + 4,
    },
    cardButtonText: { color: c.onBrand, fontWeight: "700", fontSize: type.base },
    report: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingTop: 2 },
    reportText: { color: c.onSurfaceSecondary, fontSize: type.sm },
  });
