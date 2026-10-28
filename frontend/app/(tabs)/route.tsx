// Journey planner: from a stop, my position or a point on the map, to another one.
// Waits come from live vehicles when passengers share them, otherwise from timetables or estimates.
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { Itinerary, Leg, lineLabel, PlanPlace, planRoute, searchStops, StopHit } from "@/src/api/network";
import { LineBadge } from "@/src/components/LineBadge";
import { LineMap } from "@/src/components/LineMap";
import { MapData } from "@/src/components/map-html";
import { Colors, modeColors, radius, spacing, type, useColors } from "@/src/theme";
import { formatDistance } from "@/src/utils/format";

type Field = "origin" | "destination";
type Place = PlanPlace & { lat: number; lon: number };

const WALK_COLOR = "#6B7280";
const minutes = (s: number) => `${Math.max(1, Math.round(s / 60))} min`;

export default function RouteScreen() {
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [editing, setEditing] = useState<Field | null>(null);
  const [picking, setPicking] = useState<Field | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<StopHit[]>([]);
  const [results, setResults] = useState<Itinerary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState(0);
  const [locError, setLocError] = useState(false);

  const setPlace = useCallback((field: Field, place: Place) => {
    (field === "origin" ? setOrigin : setDestination)(place);
    setEditing(null);
    setPicking(null);
    setQuery("");
    setHits([]);
  }, []);

  // Stop search, debounced.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits([]);
      return;
    }
    const timer = setTimeout(() => searchStops(q).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(timer);
  }, [query]);

  // Plan as soon as both ends are known.
  useEffect(() => {
    if (!origin || !destination) return;
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    planRoute(origin, destination)
      .then((r) => !cancelled && (setResults(r), setSelected(0)))
      .catch(() => !cancelled && (setResults(null), setFailed(true)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [origin, destination]);

  const pickMyPosition = async (field: Field) => {
    setLocError(false);
    const permission = await Location.requestForegroundPermissionsAsync();
    const pos = permission.granted
      ? await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }).catch(() => null)
      : null;
    if (!pos) {
      setLocError(true);
      return;
    }
    setPlace(field, { lat: pos.coords.latitude, lon: pos.coords.longitude, name: "Ma position" });
  };

  const swap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  const onPressMap = useCallback(
    (lat: number, lon: number) => {
      if (picking) setPlace(picking, { lat, lon, name: "Point sur la carte" });
    },
    [picking, setPlace],
  );

  const itinerary = results?.[selected];
  const mapData = useMemo<MapData>(
    () => ({
      fitKey: itinerary ? `${origin?.lat},${origin?.lon}>${destination?.lat},${destination?.lon}#${selected}` : "none",
      color: colors.brand,
      dashed: false,
      shape: [],
      stops: [],
      vehicles: [],
      paths: (itinerary?.legs ?? []).map((leg) => ({
        coords: leg.path,
        color: leg.kind === "walk" ? WALK_COLOR : leg.line?.color || modeColors[leg.line?.mode ?? "bus"],
        dashed: leg.kind === "walk",
      })),
      markers: [
        ...(origin ? [{ lat: origin.lat, lon: origin.lon, label: "A", color: "#047857" }] : []),
        ...(destination ? [{ lat: destination.lat, lon: destination.lon, label: "B", color: "#B91C1C" }] : []),
      ],
    }),
    [itinerary, origin, destination, selected, colors.brand],
  );

  const fieldRow = (field: Field, place: Place | null) => (
    <Pressable
      style={[styles.field, editing === field && styles.fieldActive]}
      onPress={() => {
        setEditing(field);
        setPicking(null);
      }}
      accessibilityLabel={field === "origin" ? "Point de départ" : "Point d'arrivée"}
    >
      <View style={[styles.fieldDot, { backgroundColor: field === "origin" ? "#047857" : "#B91C1C" }]}>
        <Text style={styles.fieldDotText}>{field === "origin" ? "A" : "B"}</Text>
      </View>
      {editing === field ? (
        <TextInput
          autoFocus
          value={query}
          onChangeText={setQuery}
          placeholder="Arrêt ou station…"
          placeholderTextColor={colors.onSurfaceSecondary}
          style={styles.input}
          autoCorrect={false}
        />
      ) : (
        <Text style={[styles.fieldText, !place && styles.placeholder]} numberOfLines={1}>
          {place?.name ?? (field === "origin" ? "Départ" : "Arrivée")}
        </Text>
      )}
    </Pressable>
  );

  return (
    <View style={styles.screen}>
      <View style={styles.form}>
        <View style={styles.fields}>
          {fieldRow("origin", origin)}
          {fieldRow("destination", destination)}
        </View>
        <Pressable style={styles.swap} onPress={swap} accessibilityLabel="Inverser départ et arrivée">
          <Ionicons name="swap-vertical" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      {editing ? (
        <ScrollView style={styles.suggestions} keyboardShouldPersistTaps="handled">
          <Pressable style={styles.suggestion} onPress={() => pickMyPosition(editing)}>
            <Ionicons name="locate" size={20} color={colors.info} />
            <Text style={styles.suggestionText}>Ma position</Text>
          </Pressable>
          {locError && <Text style={styles.error}>Position indisponible : autorisez la localisation.</Text>}
          <Pressable
            style={styles.suggestion}
            onPress={() => {
              setPicking(editing);
              setEditing(null);
            }}
          >
            <Ionicons name="map-outline" size={20} color={colors.info} />
            <Text style={styles.suggestionText}>Choisir un point sur la carte</Text>
          </Pressable>
          {hits.map((s) => (
            <Pressable key={s.id} style={styles.suggestion} onPress={() => setPlace(editing, { stop_id: s.id, name: s.name, lat: s.lat, lon: s.lon })}>
              <Ionicons name="location-outline" size={20} color={colors.onSurfaceSecondary} />
              <View style={styles.suggestionBody}>
                <Text style={styles.suggestionText} numberOfLines={1}>{s.name}</Text>
                <View style={styles.badges}>
                  {s.lines.slice(0, 5).map((l) => (
                    <LineBadge key={l.id} line={l} />
                  ))}
                </View>
              </View>
            </Pressable>
          ))}
          <Pressable style={styles.cancel} onPress={() => setEditing(null)}>
            <Text style={styles.cancelText}>Annuler</Text>
          </Pressable>
        </ScrollView>
      ) : (
        <>
          <View style={styles.mapWrap}>
            <LineMap data={mapData} onPressMap={onPressMap} style={StyleSheet.absoluteFill} />
            {picking && (
              <View style={styles.pickBanner}>
                <Text style={styles.pickText}>Touchez la carte pour choisir {picking === "origin" ? "le départ" : "l’arrivée"}</Text>
              </View>
            )}
          </View>
          <ScrollView style={styles.results} contentContainerStyle={styles.resultsContent}>
            {!origin || !destination ? (
              <Text style={styles.hint}>Choisissez un départ et une arrivée : un arrêt, votre position ou un point sur la carte.</Text>
            ) : loading ? (
              <ActivityIndicator color={colors.brand} />
            ) : failed ? (
              <Text style={styles.error}>Le serveur ne répond pas. Réessayez dans un instant.</Text>
            ) : results && results.length === 0 ? (
              <Text style={styles.hint}>Aucun trajet trouvé maintenant : la ligne ne circule peut-être plus, ou les arrêts sont trop loin (plus de 1,2 km à pied).</Text>
            ) : (
              results?.map((it, i) => (
                <Pressable key={i} style={[styles.card, i === selected && styles.cardSelected]} onPress={() => setSelected(i)}>
                  <View style={styles.cardHead}>
                    <Text style={styles.duration}>{minutes(it.duration_s)}</Text>
                    <Text style={styles.times}>{it.depart} → {it.arrive}</Text>
                    {it.live && (
                      <View style={styles.livePill}>
                        <View style={styles.liveDot} />
                        <Text style={styles.liveText}>en direct</Text>
                      </View>
                    )}
                  </View>
                  <View style={styles.summary}>
                    {it.legs.map((leg, k) => (
                      <View key={k} style={styles.summaryItem}>
                        {k > 0 && <Ionicons name="chevron-forward" size={14} color={colors.onSurfaceSecondary} />}
                        {leg.kind === "walk" ? (
                          <View style={styles.walkChip}>
                            <Ionicons name="walk" size={16} color={colors.onSurface} />
                            <Text style={styles.walkText}>{minutes(leg.duration_s)}</Text>
                          </View>
                        ) : (
                          leg.line && <LineBadge line={leg.line} />
                        )}
                      </View>
                    ))}
                  </View>
                  <Text style={styles.sub}>
                    {it.transfers === 0 ? "Sans correspondance" : `${it.transfers} correspondance${it.transfers > 1 ? "s" : ""}`} · {formatDistance(it.walk_m)} à pied
                  </Text>
                  {i === selected && <Steps legs={it.legs} styles={styles} colors={colors} />}
                </Pressable>
              ))
            )}
            {results && results.length > 0 && (
              <Text style={styles.note}>
                Trains et RFR : horaires officiels. Métro et bus : attente estimée d’après la fréquence habituelle, ou « en direct » quand un passager partage le véhicule.
              </Text>
            )}
          </ScrollView>
        </>
      )}
    </View>
  );
}

function Steps({ legs, styles, colors }: { legs: Leg[]; styles: Styles; colors: Colors }) {
  return (
    <View style={styles.steps}>
      {legs.map((leg, k) =>
        leg.kind === "walk" ? (
          <View key={k} style={styles.step}>
            <Ionicons name="walk" size={18} color={colors.onSurfaceSecondary} />
            <Text style={styles.stepText}>
              Marcher {minutes(leg.duration_s)} ({formatDistance(leg.distance_m ?? 0)}) jusqu’à {leg.to.name}
            </Text>
          </View>
        ) : (
          <View key={k} style={styles.step}>
            {leg.line && <LineBadge line={leg.line} />}
            <View style={styles.stepBody}>
              <Text style={styles.stepTitle}>
                {leg.from.name} → {leg.to.name}
              </Text>
              <Text style={styles.stepText}>
                Vers {leg.headsign} · départ {leg.depart} · {leg.stops} arrêt{(leg.stops ?? 0) > 1 ? "s" : ""} · arrivée {leg.arrive}
              </Text>
              <Text style={[styles.stepWait, leg.wait_source === "en direct" && { color: colors.ok }]}>
                Attente {minutes(leg.wait_s ?? 0)} · {leg.wait_source === "en direct" ? "véhicule en direct" : leg.wait_source === "horaire" ? "horaire officiel" : "estimation"}
              </Text>
              {leg.line && (
                <Pressable onPress={() => router.push(`/line/${leg.line!.id}`)}>
                  <Text style={styles.link}>Voir la ligne {lineLabel(leg.line)}</Text>
                </Pressable>
              )}
            </View>
          </View>
        ),
      )}
    </View>
  );
}

type Styles = ReturnType<typeof makeStyles>;

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    form: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, paddingBottom: spacing.sm },
    fields: { flex: 1, gap: spacing.sm },
    field: {
      flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 46,
      paddingHorizontal: spacing.sm + 2, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.surfaceSecondary,
    },
    fieldActive: { borderColor: c.info },
    fieldDot: { width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center" },
    fieldDotText: { color: "#FFFFFF", fontWeight: "700", fontSize: 12 },
    fieldText: { flex: 1, color: c.onSurface, fontSize: type.lg },
    placeholder: { color: c.onSurfaceSecondary },
    input: { flex: 1, color: c.onSurface, fontSize: type.lg, paddingVertical: spacing.sm },
    swap: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceSecondary },
    suggestions: { flex: 1 },
    suggestion: { flexDirection: "row", alignItems: "center", gap: spacing.sm + 4, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 4 },
    suggestionBody: { flex: 1, gap: 4 },
    suggestionText: { color: c.onSurface, fontSize: type.lg },
    badges: { flexDirection: "row", flexWrap: "wrap", gap: 4 },
    cancel: { padding: spacing.md, alignItems: "center" },
    cancelText: { color: c.info, fontWeight: "600", fontSize: type.base },
    mapWrap: { height: 260 },
    pickBanner: { position: "absolute", top: spacing.sm, left: spacing.md, right: spacing.md, backgroundColor: c.onSurface, borderRadius: radius.md, padding: spacing.sm + 2 },
    pickText: { color: c.surface, fontWeight: "600", textAlign: "center" },
    results: { flex: 1 },
    resultsContent: { padding: spacing.md, gap: spacing.sm + 4 },
    hint: { color: c.onSurfaceSecondary, fontSize: type.base, textAlign: "center", lineHeight: 20 },
    error: { color: c.error, fontSize: type.base, paddingHorizontal: spacing.md },
    card: { borderWidth: 1, borderColor: c.border, borderRadius: radius.md, padding: spacing.md - 2, gap: spacing.sm },
    cardSelected: { borderColor: c.info, borderWidth: 2 },
    cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    duration: { color: c.onSurface, fontSize: type.xl, fontWeight: "800" },
    times: { flex: 1, color: c.onSurfaceSecondary, fontSize: type.base },
    livePill: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: c.okSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
    liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: c.ok },
    liveText: { color: c.ok, fontWeight: "700", fontSize: type.sm },
    summary: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", rowGap: 6 },
    summaryItem: { flexDirection: "row", alignItems: "center", gap: 4, marginRight: 4 },
    walkChip: { flexDirection: "row", alignItems: "center", gap: 2 },
    walkText: { color: c.onSurface, fontSize: type.sm, fontWeight: "600" },
    sub: { color: c.onSurfaceSecondary, fontSize: type.sm },
    steps: { gap: spacing.sm + 4, marginTop: spacing.sm, paddingTop: spacing.sm + 4, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.border },
    step: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm + 2 },
    stepBody: { flex: 1, gap: 2 },
    stepTitle: { color: c.onSurface, fontSize: type.base, fontWeight: "700" },
    stepText: { flex: 1, color: c.onSurface, fontSize: type.base, lineHeight: 20 },
    stepWait: { color: c.onSurfaceSecondary, fontSize: type.sm },
    link: { color: c.info, fontSize: type.sm, fontWeight: "600", marginTop: 2 },
    note: { color: c.onSurfaceSecondary, fontSize: type.sm, lineHeight: 18 },
  });
