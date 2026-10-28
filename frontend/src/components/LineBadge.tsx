import { StyleSheet, Text } from "react-native";

import { LineSummary, lineLabel } from "@/src/api/network";
import { modeColors, radius, type } from "@/src/theme";

/** Black or white text, whichever reads better on the line colour (some lines are yellow). */
function textOn(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 170 ? "#111827" : "#FFFFFF";
}

export function LineBadge({ line, large = false }: { line: LineSummary; large?: boolean }) {
  const background = line.color || modeColors[line.mode] || "#374151";
  return (
    <Text
      numberOfLines={1}
      style={[styles.badge, large && styles.large, { backgroundColor: background, color: textOn(background) }]}
    >
      {lineLabel(line)}
    </Text>
  );
}

const styles = StyleSheet.create({
  badge: {
    minWidth: 44,
    maxWidth: 130,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    fontWeight: "700",
    fontSize: type.base,
    textAlign: "center",
    overflow: "hidden",
  },
  large: { fontSize: type.lg, paddingVertical: 6 },
});
