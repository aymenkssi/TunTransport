// Lines screen: search, filter by mode, live vehicles per line, and the trip being shared.
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { backendConfigured } from "@/src/api/client";
import { getLines, getLive, LineSummary, Mode } from "@/src/api/network";
import { LineBadge } from "@/src/components/LineBadge";
import { ShareBanner } from "@/src/components/ShareBanner";
import { Colors, radius, spacing, type, useColors } from "@/src/theme";

const MODES: { key: Mode; label: string }[] = [
  { key: "metro", label: "Métro" },
  { key: "bus", label: "Bus" },
  { key: "rfr", label: "RFR" },
  { key: "train", label: "Train" },
];
const MODE_ORDER: Record<string, number> = { metro: 0, rfr: 1, train: 2, bus: 3 };
const LIVE_REFRESH_MS = 30_000;

export default function LinesScreen() {
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [lines, setLines] = useState<LineSummary[] | null>(null);
  const [live, setLive] = useState<Record<string, number>>({});
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode | null>(null);

  const load = useCallback(() => {
    setError(false);
    getLines()
      .then((all) =>
        setLines(
          [...all].sort(
            (a, b) =>
              MODE_ORDER[a.mode] - MODE_ORDER[b.mode] ||
              (a.short_name || a.long_name).localeCompare(b.short_name || b.long_name, "fr", { numeric: true }),
          ),
        ),
      )
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (!backendConfigured) return;
    load();
    const refresh = () => getLive().then(setLive).catch(() => {});
    refresh();
    const timer = setInterval(refresh, LIVE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (lines ?? []).filter(
      (l) =>
        (!mode || l.mode === mode) &&
        (!q || l.short_name.toLowerCase().includes(q) || l.long_name.toLowerCase().includes(q)),
    );
  }, [lines, query, mode]);
  const liveTotal = Object.values(live).reduce((a, b) => a + b, 0);

  if (!backendConfigured) {
    return <Message styles={styles} text="Serveur non configuré : renseignez EXPO_PUBLIC_BACKEND_URL (voir frontend/.env.example)." />;
  }
  if (error) {
    return <Message styles={styles} text="Impossible de joindre le serveur." action="Réessayer" onAction={load} />;
  }
  if (!lines) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <ShareBanner />
      <View style={styles.searchRow}>
        <Ionicons name="search" size={18} color={colors.onSurfaceSecondary} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Ligne, destination…"
          placeholderTextColor={colors.onSurfaceSecondary}
          style={styles.search}
          autoCorrect={false}
          accessibilityLabel="Rechercher une ligne"
        />
      </View>
      <View style={styles.chips}>
        <Chip styles={styles} label="Tout" active={mode === null} onPress={() => setMode(null)} />
        {MODES.map((m) => (
          <Chip key={m.key} styles={styles} label={m.label} active={mode === m.key} onPress={() => setMode(mode === m.key ? null : m.key)} />
        ))}
      </View>
      <Text style={styles.summary}>
        {filtered.length} lignes · {liveTotal > 0 ? `${liveTotal} véhicule${liveTotal > 1 ? "s" : ""} en direct` : "aucun véhicule partagé pour le moment"}
      </Text>
      <FlatList
        data={filtered}
        keyExtractor={(l) => l.id}
        keyboardShouldPersistTaps="handled"
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        renderItem={({ item }) => (
          <Pressable style={({ pressed }) => [styles.row, pressed && styles.pressed]} onPress={() => router.push(`/line/${item.id}`)}>
            <LineBadge line={item} />
            <View style={styles.rowText}>
              <Text style={styles.rowTitle} numberOfLines={1}>{item.long_name}</Text>
              <Text style={styles.rowSub} numberOfLines={1}>{item.operator}</Text>
            </View>
            {live[item.id] ? (
              <View style={styles.livePill}>
                <View style={styles.liveDot} />
                <Text style={styles.liveText}>{live[item.id]}</Text>
              </View>
            ) : null}
          </Pressable>
        )}
      />
    </View>
  );
}

type Styles = ReturnType<typeof makeStyles>;

function Chip({ styles, label, active, onPress }: { styles: Styles; label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.chip, active && styles.chipActive]} accessibilityState={{ selected: active }}>
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

function Message({ styles, text, action, onAction }: { styles: Styles; text: string; action?: string; onAction?: () => void }) {
  return (
    <View style={styles.center}>
      <Text style={styles.message}>{text}</Text>
      {action && (
        <Pressable style={styles.button} onPress={onAction}>
          <Text style={styles.buttonText}>{action}</Text>
        </Pressable>
      )}
    </View>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md, backgroundColor: c.surface },
    message: { color: c.onSurface, fontSize: type.lg, textAlign: "center" },
    button: { backgroundColor: c.brand, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm + 2, borderRadius: radius.md },
    buttonText: { color: c.onBrand, fontWeight: "700", fontSize: type.base },
    searchRow: {
      flexDirection: "row", alignItems: "center", gap: spacing.sm, marginHorizontal: spacing.md, marginTop: spacing.sm,
      paddingHorizontal: spacing.sm + 4, backgroundColor: c.surfaceSecondary, borderRadius: radius.md,
    },
    search: { flex: 1, paddingVertical: spacing.sm + 2, color: c.onSurface, fontSize: type.lg },
    chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingHorizontal: spacing.md, paddingTop: spacing.sm + 4 },
    chip: { paddingHorizontal: spacing.md - 2, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: c.border },
    chipActive: { backgroundColor: c.onSurface, borderColor: c.onSurface },
    chipText: { color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    chipTextActive: { color: c.surface },
    summary: { color: c.onSurfaceSecondary, fontSize: type.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 2 },
    separator: { height: StyleSheet.hairlineWidth, backgroundColor: c.border, marginLeft: spacing.md },
    row: { flexDirection: "row", alignItems: "center", gap: spacing.sm + 4, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 4 },
    pressed: { backgroundColor: c.surfaceSecondary },
    rowText: { flex: 1 },
    rowTitle: { color: c.onSurface, fontSize: type.lg, fontWeight: "500" },
    rowSub: { color: c.onSurfaceSecondary, fontSize: type.sm },
    livePill: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: c.okSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
    liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: c.ok },
    liveText: { color: c.ok, fontWeight: "700", fontSize: type.sm },
  });
