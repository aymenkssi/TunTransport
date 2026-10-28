import "@/src/sharing/task";

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useColors } from "@/src/theme";

export default function RootLayout() {
  const colors = useColors();
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="auto" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.surface },
            headerTintColor: colors.onSurface,
            headerTitleStyle: { fontWeight: "700" },
            contentStyle: { backgroundColor: colors.surface },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false, title: "TransTunisLive" }} />
          <Stack.Screen name="line/[id]" options={{ title: "" }} />
          <Stack.Screen name="about" options={{ title: "À propos" }} />
        </Stack>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
