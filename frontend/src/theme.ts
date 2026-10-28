// TunTransport theme tokens: light surfaces, Tunisian red brand, one accent per transport mode.
import { useColorScheme } from "react-native";

const light = {
  surface: "#FFFFFF",
  onSurface: "#111827",
  surfaceSecondary: "#F3F4F6",
  onSurfaceSecondary: "#4B5563",
  border: "#E5E7EB",
  brand: "#E70013",
  onBrand: "#FFFFFF",
  ok: "#047857",
  okSoft: "#D1FAE5",
  info: "#1D4ED8",
  infoSoft: "#DBEAFE",
  warning: "#B45309",
  warningSoft: "#FEF3C7",
  error: "#B91C1C",
};

const dark: typeof light = {
  surface: "#0F1115",
  onSurface: "#F3F4F6",
  surfaceSecondary: "#1A1D24",
  onSurfaceSecondary: "#9CA3AF",
  border: "#2A303B",
  brand: "#FF3B47",
  onBrand: "#FFFFFF",
  ok: "#34D399",
  okSoft: "#064E3B",
  info: "#60A5FA",
  infoSoft: "#1E3A8A",
  warning: "#FBBF24",
  warningSoft: "#78350F",
  error: "#F87171",
};

export type Colors = typeof light;

export function useColors(): Colors {
  return useColorScheme() === "dark" ? dark : light;
}

export const modeColors: Record<string, string> = {
  metro: "#0071E3",
  bus: "#E30613",
  rfr: "#34C759",
  train: "#FF9500",
};

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 };
export const radius = { sm: 4, md: 8, lg: 16, pill: 999 };
export const type = { sm: 12, base: 14, lg: 16, xl: 20, "2xl": 24 };
