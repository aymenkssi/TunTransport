// Send a suggestion or report a data error; read by the team in the admin page.
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "@/src/api/client";
import { sendSuggestion, SuggestionCategory } from "@/src/api/network";
import { Colors, radius, spacing, type, useColors } from "@/src/theme";

const CATEGORIES: { key: SuggestionCategory; label: string; icon: "bulb-outline" | "bug-outline" | "map-outline" | "chatbubble-outline" }[] = [
  { key: "idea", label: "Idée", icon: "bulb-outline" },
  { key: "data", label: "Erreur de ligne, d’arrêt ou d’horaire", icon: "map-outline" },
  { key: "bug", label: "Problème dans l’application", icon: "bug-outline" },
  { key: "other", label: "Autre", icon: "chatbubble-outline" },
];
const MAX = 1000;

export default function SuggestionScreen() {
  const params = useLocalSearchParams<{ category?: string; line?: string; lineLabel?: string }>();
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [category, setCategory] = useState<SuggestionCategory>(
    CATEGORIES.some((c) => c.key === params.category) ? (params.category as SuggestionCategory) : "idea",
  );
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    setError(null);
    setState("sending");
    try {
      await sendSuggestion({
        category,
        message: message.trim(),
        ...(params.line ? { line_id: params.line } : {}),
        ...(contact.trim() ? { contact: contact.trim() } : {}),
      });
      setState("sent");
    } catch (e) {
      setState("idle");
      const status = e instanceof ApiError ? e.status : 0;
      setError(
        status === 429
          ? "Vous avez déjà envoyé 5 messages aujourd’hui. Merci, réessayez demain."
          : status === 422
            ? "Votre message est trop court."
            : "Envoi impossible : le serveur ne répond pas. Réessayez dans un instant.",
      );
    }
  };

  if (state === "sent") {
    return (
      <View style={styles.done}>
        <Ionicons name="checkmark-circle" size={56} color={colors.ok} />
        <Text style={styles.doneTitle}>Merci pour votre message</Text>
        <Text style={styles.hint}>L’équipe TransTunisLive le lira très bientôt.</Text>
        <Pressable style={styles.button} onPress={() => router.back()}>
          <Text style={styles.buttonText}>Retour</Text>
        </Pressable>
      </View>
    );
  }

  const ready = message.trim().length >= 5 && state === "idle";
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {params.lineLabel ? <Text style={styles.context}>Ligne concernée : {params.lineLabel}</Text> : null}
      <Text style={styles.label}>Sujet</Text>
      <View style={styles.categories}>
        {CATEGORIES.map((c) => (
          <Pressable
            key={c.key}
            style={[styles.category, category === c.key && styles.categoryActive]}
            onPress={() => setCategory(c.key)}
            accessibilityState={{ selected: category === c.key }}
          >
            <Ionicons name={c.icon} size={18} color={category === c.key ? colors.surface : colors.onSurface} />
            <Text style={[styles.categoryText, category === c.key && styles.categoryTextActive]}>{c.label}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.label}>Votre message</Text>
      <TextInput
        value={message}
        onChangeText={(t) => setMessage(t.slice(0, MAX))}
        placeholder={category === "data" ? "Ex. : l’arrêt X est mal placé, le bus ne passe plus par…" : "Écrivez votre message…"}
        placeholderTextColor={colors.onSurfaceSecondary}
        multiline
        style={styles.message}
        textAlignVertical="top"
      />
      <Text style={styles.counter}>{message.length} / {MAX}</Text>
      <Text style={styles.label}>Contact (facultatif)</Text>
      <TextInput
        value={contact}
        onChangeText={setContact}
        placeholder="E-mail ou téléphone, si vous souhaitez une réponse"
        placeholderTextColor={colors.onSurfaceSecondary}
        style={styles.input}
        autoCapitalize="none"
        keyboardType="email-address"
        maxLength={120}
      />
      {error && <Text style={styles.error}>{error}</Text>}
      <Pressable style={[styles.button, !ready && styles.disabled]} onPress={send} disabled={!ready}>
        {state === "sending" ? <ActivityIndicator color={colors.onBrand} /> : <Text style={styles.buttonText}>Envoyer</Text>}
      </Pressable>
      <Text style={styles.hint}>Votre message est lu par l’équipe TransTunisLive. N’y mettez pas d’informations sensibles.</Text>
    </ScrollView>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    content: { padding: spacing.md, gap: spacing.sm + 2 },
    context: { color: c.onSurface, fontSize: type.base, fontWeight: "600", backgroundColor: c.surfaceSecondary, padding: spacing.sm + 4, borderRadius: radius.md },
    label: { color: c.onSurfaceSecondary, fontSize: type.sm, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5, marginTop: spacing.sm },
    categories: { gap: spacing.sm },
    category: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.sm + 4, borderRadius: radius.md, borderWidth: 1, borderColor: c.border },
    categoryActive: { backgroundColor: c.onSurface, borderColor: c.onSurface },
    categoryText: { color: c.onSurface, fontSize: type.base, fontWeight: "600" },
    categoryTextActive: { color: c.surface },
    message: { minHeight: 140, color: c.onSurface, fontSize: type.lg, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, padding: spacing.sm + 4 },
    counter: { color: c.onSurfaceSecondary, fontSize: type.sm, alignSelf: "flex-end" },
    input: { color: c.onSurface, fontSize: type.lg, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, padding: spacing.sm + 4 },
    error: { color: c.error, fontSize: type.base },
    button: { backgroundColor: c.brand, borderRadius: radius.md, paddingVertical: spacing.sm + 6, alignItems: "center", marginTop: spacing.sm },
    buttonText: { color: c.onBrand, fontSize: type.lg, fontWeight: "700" },
    disabled: { opacity: 0.5 },
    hint: { color: c.onSurfaceSecondary, fontSize: type.sm, textAlign: "center", lineHeight: 18 },
    done: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: c.surface },
    doneTitle: { color: c.onSurface, fontSize: type.xl, fontWeight: "700" },
  });
