import { Ionicons } from "@expo/vector-icons";
import { router, Tabs } from "expo-router";
import { Pressable } from "react-native";

import { useColors } from "@/src/theme";

export default function TabsLayout() {
  const colors = useColors();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTintColor: colors.onSurface,
        headerTitleStyle: { fontWeight: "700" },
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.onSurfaceSecondary,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        sceneStyle: { backgroundColor: colors.surface },
        headerRight: () => (
          <Pressable onPress={() => router.push("/about")} hitSlop={12} style={{ marginRight: 16 }} accessibilityLabel="À propos et confidentialité">
            <Ionicons name="information-circle-outline" size={24} color={colors.onSurface} />
          </Pressable>
        ),
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "TransTunisLive",
          tabBarLabel: "Carte",
          tabBarIcon: ({ color, size }) => <Ionicons name="map" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="lines"
        options={{
          title: "Lignes",
          tabBarIcon: ({ color, size }) => <Ionicons name="list" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}
