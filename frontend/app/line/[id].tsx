// Line screen: map with live vehicles, direction, stops with live ETA or timetable, and trip sharing.
import { Ionicons } from "@expo/vector-icons";
import { Stack, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, FlatList, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { getLine, getVehicles, Line, Vehicle } from "@/src/api/network";
import { LineBadge } from "@/src/components/LineBadge";
import { LineMap } from "@/src/components/LineMap";
import { MapData } from "@/src/components/map-html";
import { confirmReport } from "@/src/components/report";
import { startSharing, stopSharing } from "@/src/sharing/session";
import { useShare } from "@/src/sharing/use-share";
import { Colors, modeColors, radius, spacing, type, useColors } from "@/src/theme";
import { formatAge, formatEta, nextTimes } from "@/src/utils/format";

const VEHICLES_REFRESH_MS = 10_000;
const MODE_TITLES: Record<string, string> = { bus: "Bus", metro: "Métro", rfr: "RFR", train: "Train" };

const SHARE_STATUS: Record<string, string> = {
  checking: "Vérification du trajet… restez quelques secondes dans le véhicule.",
  on_route: "Position partagée : les autres voyageurs voient ce véhicule.",
  offline: "Connexion perdue, nouvel essai en cours…",
};

export default function LineScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const share = useShare();
  const [line, setLine] = useState<Line | null>(null);
  const [error, setError] = useState(false);
  const [direction, setDirection] = useState(0);
  const [selectedStop, setSelectedStop] = useState<string | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [busy, setBusy] = useState(false);

  const sharingHere = share?.lineId === id;
  const shownDirection = sharingHere ? share.direction : direction;

  useEffect(() => {
    getLine(id).then(setLine).catch(() => setError(true));
  }, [id]);

  const refreshVehicles = useCallback(() => {
    getVehicles(id, selectedStop ?? undefined).then(setVehicles).catch(() => {});
  }, [id, selectedStop]);

  useEffect(() => {
    refreshVehicles();
    const timer = setInterval(refreshVehicles, VEHICLES_REFRESH_MS);
    return () => clearInterval(timer);
  }, [refreshVehicles]);

  const dir = line?.directions[shownDirection];
  const shown = useMemo(() => vehicles.filter((v) => v.direction === shownDirection), [vehicles, shownDirection]);
  const stopsById = useMemo(() => new Map(line?.stops.map((s) => [s.id, s]) ?? []), [line]);
  const color = line?.color || (line ? modeColors[line.mode] : colors.brand);

  const mapData = useMemo<MapData | null>(() => {
    if (!line || !dir) return null;
    return {
      fitKey: `${line.id}:${shownDirection}`,
      color,
      dashed: line.shape_source !== "tunismapper",
      shape: dir.shape,
      stops: dir.stops.flatMap((ds) => {
        const s = stopsById.get(ds.id);
        return s ? [{ id: s.id, name: s.name, lat: s.lat, lon: s.lon, selected: s.id === selectedStop }] : [];
      }),
      vehicles: shown,
    };
  }, [line, dir, shownDirection, color, stopsById, selectedStop, shown]);

  const onSelectStop = useCallback((stopId: string) => setSelectedStop((cur) => (cur === stopId ? null : stopId)), []);

  const onShare = async () => {
    if (!line) return;
    if (share && !sharingHere) {
      Alert.alert("Un partage est déjà en cours", `Arrêtez d'abord le partage de la ligne ${share.lineLabel}.`);
      return;
    }
    setBusy(true);
    const result = await startSharing(line, shownDirection);
    setBusy(false);
    if (result === "denied") {
      Alert.alert("Localisation refusée", "Autorisez la localisation pour partager la position du véhicule.");
    } else if (result === "error") {
      Alert.alert("Partage impossible", "Le serveur ne répond pas. Réessayez dans un instant.");
    }
  };

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.text}>Ligne introuvable ou serveur injoignable.</Text>
      </View>
    );
  }
  if (!line || !dir || !mapData) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

  const now = new Date();
  const selectedName = selectedStop ? stopsById.get(selectedStop)?.name : null;
  const etaVehicles = selectedStop ? shown.filter((v) => v.eta_s !== null) : [];

  const header = (
    <View>
      <LineMap data={mapData} onSelectStop={onSelectStop} style={styles.map} />
      <View style={styles.block}>
        <View style={styles.titleRow}>
          <LineBadge line={line} large />
          <Text style={styles.title} numberOfLines={2}>{line.long_name}</Text>
        </View>
        {line.shape_source !== "tunismapper" && (
          <Text style={styles.note}>Tracé approximatif (arrêts reliés en ligne droite).</Text>
        )}

        {!sharingHere && (
          <View style={styles.directions}>
            {line.directions.map((d, i) => (
              <Pressable
                key={i}
                onPress={() => setDirection(i)}
                style={[styles.direction, i === shownDirection && styles.directionActive]}
                accessibilityState={{ selected: i === shownDirection }}
              >
                <Ionicons name="arrow-forward" size={14} color={i === shownDirection ? colors.surface : colors.onSurface} />
                <Text style={[styles.directionText, i === shownDirection && styles.directionTextActive]} numberOfLines={1}>
                  {d.headsign}
                </Text>
              </Pressable>
            ))}
          </View>
        )}

        {sharingHere ? (
          <View style={styles.shareCard}>
            <Text style={styles.shareTitle}>Vous partagez ce trajet vers {share.headsign}</Text>
            <Text style={styles.text}>
              {share.status === "rejected" ? `Non diffusé : ${share.reason}.` : SHARE_STATUS[share.status]}
            </Text>
            {share.speedMps !== null && share.status === "on_route" && (
              <Text style={styles.sub}>{Math.round(share.speedMps * 3.6)} km/h</Text>
            )}
            <Pressable style={styles.stopButton} onPress={stopSharing}>
              <Text style={styles.stopButtonText}>Arrêter le partage</Text>
            </Pressable>
          </View>
        ) : (
          <Pressable style={[styles.shareButton, busy && styles.disabled]} onPress={onShare} disabled={busy}>
            <Ionicons name="radio-outline" size={18} color={colors.onBrand} />
            <Text style={styles.shareButtonText}>Je suis dans ce véhicule</Text>
          </Pressable>
        )}
        {!sharingHere && (
          <Text style={styles.note}>
            Votre position n’est diffusée que pendant le trajet, une fois vérifiée sur la ligne. Aucune position n’est conservée ensuite.
            {Platform.OS === "web" ? " Sur le web, gardez la page ouverte." : ""}
          </Text>
        )}

        <Text style={styles.section}>En direct</Text>
        {shown.length === 0 ? (
          <Text style={styles.sub}>Aucun véhicule partagé dans ce sens. Horaires théoriques ci-dessous.</Text>
        ) : (
          shown.map((v, i) => (
            <View key={i} style={styles.vehicle}>
              <View style={[styles.statusDot, { backgroundColor: v.status === "fiable" ? colors.ok : v.status === "probable" ? colors.info : colors.onSurfaceSecondary }]} />
              <Text style={[styles.text, styles.vehicleText]}>
                {v.status === "fiable" ? "Fiable" : v.status === "probable" ? "Probable" : "Obsolète"} · {v.confirmations} passager{v.confirmations > 1 ? "s" : ""} · {formatAge(v.age_s)}
              </Text>
              {!sharingHere && (
                <Pressable onPress={() => confirmReport(line.id, v, refreshVehicles)} hitSlop={8} accessibilityLabel="Signaler ce véhicule">
                  <Ionicons name="flag-outline" size={16} color={colors.onSurfaceSecondary} />
                </Pressable>
              )}
            </View>
          ))
        )}

        {selectedName && (
          <View style={styles.etaCard}>
            <Text style={styles.shareTitle}>À {selectedName}</Text>
            {etaVehicles.length === 0 ? (
              <Text style={styles.sub}>Aucun véhicule en approche signalé.</Text>
            ) : (
              etaVehicles.map((v, i) => (
                <Text key={i} style={styles.text}>
                  {formatEta(v.eta_s ?? 0)} · {v.status}
                </Text>
              ))
            )}
          </View>
        )}

        <Text style={styles.section}>Arrêts · touchez un arrêt pour l’heure d’arrivée</Text>
      </View>
    </View>
  );

  return (
    <View style={styles.screen}>
      <Stack.Screen options={{ title: `${MODE_TITLES[line.mode]} ${line.short_name}`.trim() }} />
      <FlatList
        data={dir.stops}
        keyExtractor={(s) => s.id}
        ListHeaderComponent={header}
        renderItem={({ item, index }) => {
          const stop = stopsById.get(item.id);
          if (!stop) return null;
          const times = nextTimes(line.timetable[stop.id]?.[dir.headsign], now);
          const selected = item.id === selectedStop;
          return (
            <Pressable style={[styles.stop, selected && styles.stopSelected]} onPress={() => onSelectStop(item.id)}>
              <View style={styles.rail}>
                <View style={[styles.railLine, { backgroundColor: color }, index === 0 && styles.railFirst, index === dir.stops.length - 1 && styles.railLast]} />
                <View style={[styles.railDot, { borderColor: color }]} />
              </View>
              <Text style={[styles.stopName, selected && styles.stopNameSelected]} numberOfLines={1}>{stop.name}</Text>
              <Text style={styles.sub}>{times.join("  ")}</Text>
            </Pressable>
          );
        }}
      />
    </View>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: c.surface },
    map: { height: 300, width: "100%" },
    block: { padding: spacing.md, gap: spacing.sm + 2 },
    titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm + 4 },
    title: { flex: 1, color: c.onSurface, fontSize: type.xl, fontWeight: "700" },
    text: { color: c.onSurface, fontSize: type.base },
    sub: { color: c.onSurfaceSecondary, fontSize: type.sm },
    note: { color: c.onSurfaceSecondary, fontSize: type.sm },
    section: { color: c.onSurfaceSecondary, fontSize: type.sm, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.sm },
    directions: { flexDirection: "row", gap: spacing.sm },
    direction: {
      flex: 1, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.sm + 4, paddingVertical: spacing.sm,
      borderRadius: radius.md, borderWidth: 1, borderColor: c.border,
    },
    directionActive: { backgroundColor: c.onSurface, borderColor: c.onSurface },
    directionText: { flex: 1, color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    directionTextActive: { color: c.surface },
    shareButton: {
      flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
      backgroundColor: c.brand, borderRadius: radius.md, paddingVertical: spacing.sm + 6,
    },
    shareButtonText: { color: c.onBrand, fontSize: type.lg, fontWeight: "700" },
    disabled: { opacity: 0.5 },
    shareCard: { backgroundColor: c.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, gap: 6, borderLeftWidth: 4, borderLeftColor: c.brand },
    shareTitle: { color: c.onSurface, fontSize: type.base, fontWeight: "700" },
    stopButton: { alignSelf: "flex-start", marginTop: 4, borderWidth: 1, borderColor: c.error, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
    stopButtonText: { color: c.error, fontWeight: "700", fontSize: type.base },
    vehicle: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    statusDot: { width: 10, height: 10, borderRadius: 5 },
    vehicleText: { flex: 1 },
    etaCard: { backgroundColor: c.infoSoft, borderRadius: radius.md, padding: spacing.md - 4, gap: 4 },
    stop: { flexDirection: "row", alignItems: "center", gap: spacing.sm + 4, paddingRight: spacing.md, minHeight: 44 },
    stopSelected: { backgroundColor: c.surfaceSecondary },
    rail: { width: 40, alignSelf: "stretch", alignItems: "center", justifyContent: "center" },
    railLine: { position: "absolute", top: 0, bottom: 0, width: 4 },
    railFirst: { top: "50%" },
    railLast: { bottom: "50%" },
    railDot: { width: 14, height: 14, borderRadius: 7, borderWidth: 3, backgroundColor: c.surface },
    stopName: { flex: 1, color: c.onSurface, fontSize: type.base },
    stopNameSelected: { fontWeight: "700" },
  });
