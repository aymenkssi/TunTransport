import "@/src/sharing/task";

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { Platform, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { initAds } from "@/src/ads";
import { LiveSharers } from "@/src/components/LiveSharers";
import { useColors } from "@/src/theme";

export default function RootLayout() {
  const colors = useColors();
  useEffect(() => {
    initAds(); // consentement (si la loi l'exige), puis publicités
  }, []);
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
            // The native header (Android) already pads its right edge; the web one does not.
            headerRight: () => (
              <View style={{ marginRight: Platform.OS === "web" ? 16 : 0 }}>
                <LiveSharers />
              </View>
            ),
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false, title: "TransTunisLive" }} />
          <Stack.Screen name="line/[id]" options={{ title: "" }} />
          <Stack.Screen name="about" options={{ title: "À propos" }} />
          <Stack.Screen name="suggestion" options={{ title: "Envoyer une suggestion" }} />
        </Stack>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
