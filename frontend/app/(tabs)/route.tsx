// Journey planner: from a stop, my position or a point on the map, to another one.
// Waits come from live vehicles when passengers share them, otherwise from timetables or estimates.
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, BackHandler, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import {
  Itinerary,
  Leg,
  lineLabel,
  PlaceHit,
  PlanPlace,
  planRoute,
  RoadMode,
  roadRoute,
  RoadRoute,
  searchPlaces,
  searchStops,
  StopHit,
} from "@/src/api/network";
import AdBanner from "@/src/ads/AdBanner";
import { LineBadge } from "@/src/components/LineBadge";
import { LineMap } from "@/src/components/LineMap";
import { MapData } from "@/src/components/map-html";
import { Colors, modeColors, radius, spacing, type, useColors } from "@/src/theme";
import { formatDistance } from "@/src/utils/format";

type Field = "origin" | "destination";
type Place = PlanPlace & { lat: number; lon: number };

const WALK_COLOR = "#6B7280";
const CAR_COLOR = "#2563EB";

type TravelMode = "transit" | RoadMode;
const TRAVEL_MODES: { key: TravelMode; label: string; icon: "bus" | "car" | "walk" }[] = [
  { key: "transit", label: "Transports", icon: "bus" },
  { key: "car", label: "Voiture", icon: "car" },
  { key: "foot", label: "À pied", icon: "walk" },
];

type DepartChoice = { label: string; at: () => number | null };
const tomorrowAt = (h: number) => () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(h, 0, 0, 0);
  return Math.floor(d.getTime() / 1000);
};
const inMinutes = (m: number) => () => Math.floor(Date.now() / 1000) + m * 60;
const DEPART_CHOICES: DepartChoice[] = [
  { label: "Maintenant", at: () => null },
  { label: "Dans 30 min", at: inMinutes(30) },
  { label: "Dans 1 h", at: inMinutes(60) },
  { label: "Dans 2 h", at: inMinutes(120) },
  { label: "Demain 7 h", at: tomorrowAt(7) },
  { label: "Demain 9 h", at: tomorrowAt(9) },
];

/** "Demain", "Après-demain" or a date, when the trip is not today. */
function dayLabel(date: string): string | null {
  const today = new Date();
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (!date || date === iso(today)) return null;
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  if (date === iso(tomorrow)) return "Demain";
  const [y, m, d] = date.split("-");
  return `Le ${d}/${m}${y === String(today.getFullYear()) ? "" : `/${y}`}`;
}
const minutes = (s: number) => {
  const m = Math.max(1, Math.round(s / 60));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
};

export default function RouteScreen() {
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [editing, setEditing] = useState<Field | null>(null);
  const [picking, setPicking] = useState<Field | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<StopHit[]>([]);
  // Addresses: local index while typing; `full` adds the whole country (Nominatim) on submit.
  const [addresses, setAddresses] = useState<{ query: string; hits: PlaceHit[] | null; failed: boolean; full: boolean } | null>(null);
  const [results, setResults] = useState<Itinerary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState(0);
  // Enlarged view: the map alone, or the itinerary list alone (the form is hidden in both).
  const [expanded, setExpanded] = useState<"map" | "list" | null>(null);
  const [locError, setLocError] = useState(false);
  const [departChoice, setDepartChoice] = useState(0);
  const [travelMode, setTravelMode] = useState<TravelMode>("transit");
  const [road, setRoad] = useState<RoadRoute | null>(null);
  const [choosingTime, setChoosingTime] = useState(false);

  const setPlace = useCallback((field: Field, place: Place) => {
    (field === "origin" ? setOrigin : setDestination)(place);
    setEditing(null);
    setPicking(null);
    setQuery("");
    setHits([]);
    setAddresses(null);
  }, []);

  const findAddress = () => {
    const q = query.trim();
    if (q.length < 3) return;
    setAddresses((cur) => ({ query: q, hits: cur?.query === q ? cur.hits : null, failed: false, full: true }));
    searchPlaces(q)
      .then((found) => setAddresses({ query: q, hits: found, failed: false, full: true }))
      .catch(() => setAddresses((cur) => ({ query: q, hits: cur?.hits ?? [], failed: true, full: true })));
  };

  // Stops and addresses while typing, debounced.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits([]);
      setAddresses(null);
      return;
    }
    const timer = setTimeout(() => {
      searchStops(q).then(setHits).catch(() => setHits([]));
      searchPlaces(q, true)
        .then((found) => setAddresses((cur) => (cur?.full && cur.query === q ? cur : { query: q, hits: found, failed: false, full: false })))
        .catch(() => {});
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  // Plan as soon as both ends are known, and again when the departure time changes.
  useEffect(() => {
    if (!origin || !destination) return;
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    const departAt = DEPART_CHOICES[departChoice].at();
    const done = () => !cancelled && setLoading(false);
    if (travelMode === "transit") {
      setRoad(null);
      planRoute(origin, destination, departAt)
        .then((r) => !cancelled && (setResults(r), setSelected(0)))
        .catch(() => !cancelled && (setResults(null), setFailed(true)))
        .finally(done);
    } else {
      setResults(null);
      roadRoute(origin, destination, travelMode, departAt)
        .then((r) => !cancelled && setRoad(r))
        .catch(() => !cancelled && (setRoad(null), setFailed(true)))
        .finally(done);
    }
    return () => {
      cancelled = true;
    };
  }, [origin, destination, departChoice, travelMode]);

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

  useEffect(() => {
    if (!expanded) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      setExpanded(null);
      return true;
    });
    return () => sub.remove();
  }, [expanded]);

  const itinerary = travelMode === "transit" ? results?.[selected] : undefined;
  const mapData = useMemo<MapData>(
    () => ({
      fitKey:
        itinerary || road
          ? `${origin?.lat},${origin?.lon}>${destination?.lat},${destination?.lon}#${travelMode}${selected}#${expanded === "map"}`
          : "none",
      color: colors.brand,
      dashed: false,
      shape: [],
      stops: [],
      vehicles: [],
      paths: road
        ? [{ coords: road.path, color: road.mode === "car" ? CAR_COLOR : WALK_COLOR, dashed: road.mode === "foot" }]
        : (itinerary?.legs ?? []).map((leg) => ({
            coords: leg.path,
            color: leg.kind === "walk" ? WALK_COLOR : leg.line?.color || modeColors[leg.line?.mode ?? "bus"],
            dashed: leg.kind === "walk",
          })),
      markers: [
        ...(origin ? [{ lat: origin.lat, lon: origin.lon, label: "A", color: "#047857" }] : []),
        ...(destination ? [{ lat: destination.lat, lon: destination.lon, label: "B", color: "#B91C1C" }] : []),
      ],
    }),
    [itinerary, road, travelMode, origin, destination, selected, colors.brand],
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
          placeholder="Arrêt, adresse ou lieu…"
          placeholderTextColor={colors.onSurfaceSecondary}
          style={styles.input}
          autoCorrect={false}
          returnKeyType="search"
          onSubmitEditing={findAddress}
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
      {expanded === "list" && (
        <Pressable style={styles.compactBar} onPress={() => setExpanded(null)} accessibilityLabel="Réduire la liste">
          <Text style={styles.compactText} numberOfLines={1}>
            {origin?.name ?? "Départ"} → {destination?.name ?? "Arrivée"}
          </Text>
          <Ionicons name="contract" size={18} color={colors.onSurface} />
        </Pressable>
      )}
      {!expanded && (
      <View style={styles.form}>
        <View style={styles.fields}>
          {fieldRow("origin", origin)}
          {fieldRow("destination", destination)}
        </View>
        <Pressable style={styles.swap} onPress={swap} accessibilityLabel="Inverser départ et arrivée">
          <Ionicons name="swap-vertical" size={22} color={colors.onSurface} />
        </Pressable>
      </View>
      )}
      {!editing && !expanded && (
        <View style={styles.modes}>
          {TRAVEL_MODES.map((m) => (
            <Pressable
              key={m.key}
              style={[styles.mode, travelMode === m.key && styles.modeActive]}
              onPress={() => setTravelMode(m.key)}
              accessibilityState={{ selected: travelMode === m.key }}
            >
              <Ionicons name={m.icon} size={16} color={travelMode === m.key ? colors.surface : colors.onSurface} />
              <Text style={[styles.modeText, travelMode === m.key && styles.modeTextActive]}>{m.label}</Text>
            </Pressable>
          ))}
        </View>
      )}
      {!editing && !expanded && (
        <View style={styles.timeRow}>
          <Pressable style={styles.timeButton} onPress={() => setChoosingTime((v) => !v)} accessibilityLabel="Heure de départ">
            <Ionicons name="time-outline" size={16} color={colors.onSurface} />
            <Text style={styles.timeText}>Départ : {DEPART_CHOICES[departChoice].label.toLowerCase()}</Text>
            <Ionicons name={choosingTime ? "chevron-up" : "chevron-down"} size={14} color={colors.onSurfaceSecondary} />
          </Pressable>
          {choosingTime && (
            <View style={styles.timeChoices}>
              {DEPART_CHOICES.map((c, i) => (
                <Pressable
                  key={c.label}
                  style={[styles.timeChip, i === departChoice && styles.timeChipActive]}
                  onPress={() => {
                    setDepartChoice(i);
                    setChoosingTime(false);
                  }}
                >
                  <Text style={[styles.timeChipText, i === departChoice && styles.timeChipTextActive]}>{c.label}</Text>
                </Pressable>
              ))}
            </View>
          )}
        </View>
      )}

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
          {hits.length > 0 && <Text style={styles.sectionLabel}>Arrêts</Text>}
          {hits.slice(0, 5).map((s) => (
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
          {addresses && (addresses.hits === null || addresses.hits.length > 0 || addresses.full) && (
            <>
              <Text style={styles.sectionLabel}>Adresses et lieux</Text>
              {addresses.hits === null ? (
                <ActivityIndicator color={colors.brand} style={styles.addressLoading} />
              ) : addresses.failed ? (
                <Text style={styles.error}>Recherche d’adresse indisponible pour le moment.</Text>
              ) : addresses.hits.length === 0 ? (
                <Text style={styles.empty}>Aucune adresse trouvée pour « {addresses.query} ».</Text>
              ) : (
                addresses.hits.map((h, k) => (
                  <Pressable key={k} style={styles.suggestion} onPress={() => setPlace(editing, { lat: h.lat, lon: h.lon, name: h.name })}>
                    <Ionicons name="home-outline" size={20} color={colors.onSurfaceSecondary} />
                    <View style={styles.suggestionBody}>
                      <Text style={styles.suggestionText} numberOfLines={1}>{h.name}</Text>
                      {h.detail ? <Text style={styles.detail} numberOfLines={1}>{h.detail}</Text> : null}
                      {h.stop_distance_m !== null && h.stop_distance_m > 1200 && (
                        <Text style={styles.far}>Loin du réseau : arrêt le plus proche à {formatDistance(h.stop_distance_m)}</Text>
                      )}
                    </View>
                  </Pressable>
                ))
              )}
              <Text style={styles.credit}>Adresses © contributeurs OpenStreetMap</Text>
            </>
          )}
          {query.trim().length >= 3 && !(addresses?.full && addresses.query === query.trim()) && (
            <Pressable style={styles.suggestion} onPress={findAddress}>
              <Ionicons name="search" size={20} color={colors.info} />
              <Text style={styles.suggestionText} numberOfLines={1}>
                Chercher « {query.trim()} » dans toute la Tunisie
              </Text>
            </Pressable>
          )}
          <Pressable style={styles.cancel} onPress={() => setEditing(null)}>
            <Text style={styles.cancelText}>Annuler</Text>
          </Pressable>
        </ScrollView>
      ) : (
        <>
          <View style={expanded === "map" ? styles.mapFull : expanded === "list" ? styles.mapHidden : styles.mapWrap}>
            <LineMap data={mapData} onPressMap={onPressMap} style={StyleSheet.absoluteFill} />
            {!picking && expanded !== "list" && (
              <Pressable
                style={styles.expandButton}
                onPress={() => setExpanded(expanded === "map" ? null : "map")}
                accessibilityLabel={expanded === "map" ? "Réduire la carte" : "Agrandir la carte"}
                hitSlop={6}
              >
                <Ionicons name={expanded === "map" ? "contract" : "expand"} size={20} color={colors.onSurface} />
              </Pressable>
            )}
            {expanded === "map" && (itinerary || road) && (
              <Pressable style={styles.stepsButton} onPress={() => setExpanded("list")}>
                <Ionicons name="list" size={18} color={colors.surface} />
                <Text style={styles.stepsButtonText}>Voir les étapes</Text>
              </Pressable>
            )}
            {picking && (
              <View style={styles.pickBanner}>
                <Text style={styles.pickText}>Touchez la carte pour choisir {picking === "origin" ? "le départ" : "l’arrivée"}</Text>
              </View>
            )}
          </View>
          {expanded !== "map" && (
          <>
          {origin && destination && !loading && (results?.length || road) ? (
            <Pressable
              style={styles.resultsHandle}
              onPress={() => setExpanded(expanded === "list" ? null : "list")}
              accessibilityLabel={expanded === "list" ? "Réduire la liste" : "Agrandir la liste"}
            >
              <View style={styles.handleBar} />
              <Ionicons name={expanded === "list" ? "chevron-down" : "chevron-up"} size={16} color={colors.onSurfaceSecondary} />
              <Text style={styles.handleText}>{expanded === "list" ? "Réduire" : "Agrandir"}</Text>
            </Pressable>
          ) : null}
          <ScrollView style={styles.results} contentContainerStyle={styles.resultsContent}>
            {!origin || !destination ? (
              <Text style={styles.hint}>Choisissez un départ et une arrivée : un arrêt, votre position ou un point sur la carte.</Text>
            ) : loading ? (
              <ActivityIndicator color={colors.brand} />
            ) : failed ? (
              <Text style={styles.error}>
                {travelMode === "transit"
                  ? "Le serveur ne répond pas. Réessayez dans un instant."
                  : "Calcul d’itinéraire indisponible pour le moment, ou aucun chemin entre ces deux points."}
              </Text>
            ) : road ? (
              <RoadCard road={road} styles={styles} colors={colors} />
            ) : results && results.length === 0 ? (
              <Text style={styles.hint}>Aucun trajet trouvé : le départ ou l’arrivée est à plus de 1,2 km à pied d’un arrêt desservi. Essayez un point plus proche d’une ligne.</Text>
            ) : (
              <>
              {results?.[0]?.later && (
                <View style={styles.laterBanner}>
                  <Ionicons name="moon-outline" size={18} color={colors.warning} />
                  <Text style={styles.laterText}>
                    Plus de transport à cette heure. Premier trajet possible : {(dayLabel(results[0].date) ?? "aujourd’hui").toLowerCase()} à {results[0].depart}.
                  </Text>
                </View>
              )}
              {results?.map((it, i) => (
                <Pressable key={i} style={[styles.card, i === selected && styles.cardSelected]} onPress={() => setSelected(i)}>
                  <View style={styles.cardHead}>
                    <Text style={styles.duration}>{minutes(it.duration_s)}</Text>
                    <Text style={styles.times}>
                      {dayLabel(it.date) ? `${dayLabel(it.date)} ` : ""}{it.depart} → {it.arrive}
                    </Text>
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
              ))}
              </>
            )}
            {travelMode === "transit" && results && results.length > 0 && (
              <Text style={styles.note}>
                Trains et RFR : horaires officiels. Métro et bus : attente estimée d’après la fréquence habituelle, ou « en direct » quand un passager partage le véhicule.
              </Text>
            )}
          </ScrollView>
          </>
          )}
          <AdBanner />
        </>
      )}
    </View>
  );
}

function RoadCard({ road, styles, colors }: { road: RoadRoute; styles: Styles; colors: Colors }) {
  const day = dayLabel(road.date);
  return (
    <View style={[styles.card, styles.cardSelected]}>
      <View style={styles.cardHead}>
        <Ionicons name={road.mode === "car" ? "car" : "walk"} size={22} color={colors.onSurface} />
        <Text style={styles.duration}>{minutes(road.duration_s)}</Text>
        <Text style={styles.times}>
          {day ? `${day} ` : ""}
          {road.depart} → {road.arrive}
        </Text>
      </View>
      <Text style={styles.sub}>
        {formatDistance(road.distance_m)}
        {road.mode === "car" ? " · durée sans trafic : comptez plus aux heures de pointe" : " · à pied, environ 5 km/h"}
      </Text>
      <View style={styles.steps}>
        {road.steps.map((s, k) => (
          <View key={k} style={styles.step}>
            <Ionicons name={k === road.steps.length - 1 ? "flag" : "arrow-forward"} size={16} color={colors.onSurfaceSecondary} />
            <View style={styles.stepBody}>
              <Text style={styles.stepText}>{s.instruction}</Text>
              {s.distance_m > 0 && <Text style={styles.stepWait}>{formatDistance(s.distance_m)}</Text>}
            </View>
          </View>
        ))}
      </View>
      <Text style={styles.credit}>Itinéraire © contributeurs OpenStreetMap (OSRM)</Text>
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
                {leg.wait_s ? `Attente ${minutes(leg.wait_s)}` : "Sans attente"} · {leg.wait_source === "en direct" ? "véhicule en direct" : leg.wait_source === "horaire" ? "horaire officiel" : "estimation"}
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
    sectionLabel: { color: c.onSurfaceSecondary, fontSize: type.sm, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5, paddingHorizontal: spacing.md, paddingTop: spacing.sm },
    addressLoading: { padding: spacing.md },
    empty: { color: c.onSurfaceSecondary, fontSize: type.sm, paddingHorizontal: spacing.md },
    detail: { color: c.onSurfaceSecondary, fontSize: type.sm },
    far: { color: c.warning, fontSize: type.sm },
    credit: { color: c.onSurfaceSecondary, fontSize: 11, paddingHorizontal: spacing.md, paddingTop: spacing.sm },
    cancelText: { color: c.info, fontWeight: "600", fontSize: type.base },
    mapWrap: { height: 260 },
    mapFull: { flex: 1 },
    mapHidden: { height: 0, overflow: "hidden" },
    expandButton: {
      position: "absolute", top: spacing.sm, right: spacing.sm, width: 40, height: 40, borderRadius: 20,
      alignItems: "center", justifyContent: "center", backgroundColor: c.surface, elevation: 3,
      shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 4, shadowOffset: { width: 0, height: 1 },
    },
    stepsButton: {
      position: "absolute", bottom: 72, alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 6,
      backgroundColor: c.onSurface, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 2, borderRadius: radius.pill, elevation: 3,
    },
    stepsButtonText: { color: c.surface, fontWeight: "700", fontSize: type.base },
    compactBar: {
      flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 2,
      borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.border,
    },
    compactText: { flex: 1, color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    resultsHandle: {
      flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 6,
      borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.border,
    },
    handleBar: { position: "absolute", top: 3, width: 36, height: 4, borderRadius: 2, backgroundColor: c.border },
    handleText: { color: c.onSurfaceSecondary, fontSize: type.sm, fontWeight: "600" },
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
    modes: { flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
    mode: {
      flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
      paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: c.border,
    },
    modeActive: { backgroundColor: c.onSurface, borderColor: c.onSurface },
    modeText: { color: c.onSurface, fontSize: type.sm, fontWeight: "700" },
    modeTextActive: { color: c.surface },
    timeRow: { paddingHorizontal: spacing.md, paddingBottom: spacing.sm, gap: spacing.sm },
    timeButton: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", paddingVertical: 4 },
    timeText: { color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    timeChoices: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
    timeChip: { paddingHorizontal: spacing.sm + 4, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: c.border },
    timeChipActive: { backgroundColor: c.onSurface, borderColor: c.onSurface },
    timeChipText: { color: c.onSurface, fontSize: type.sm, fontWeight: "600" },
    timeChipTextActive: { color: c.surface },
    laterBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: c.warningSoft, borderRadius: radius.md, padding: spacing.sm + 4 },
    laterText: { flex: 1, color: c.onSurface, fontSize: type.base, lineHeight: 20 },
  });
