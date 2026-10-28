// Banner shown while the user shares a trip: tap to go back to that line.
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text } from "react-native";

import { useShare } from "@/src/sharing/use-share";
import { radius, spacing, type, useColors } from "@/src/theme";

export function ShareBanner() {
  const colors = useColors();
  const share = useShare();
  if (!share) return null;
  return (
    <Pressable style={[styles.banner, { backgroundColor: colors.brand }]} onPress={() => router.push(`/line/${share.lineId}`)}>
      <Ionicons name="radio" size={18} color={colors.onBrand} />
      <Text style={[styles.text, { color: colors.onBrand }]} numberOfLines={1}>
        Vous partagez {share.lineLabel} vers {share.headsign}
      </Text>
      <Ionicons name="chevron-forward" size={18} color={colors.onBrand} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginHorizontal: spacing.md, marginTop: spacing.sm, padding: spacing.sm + 4, borderRadius: radius.md,
  },
  text: { flex: 1, fontWeight: "600", fontSize: type.base },
});
