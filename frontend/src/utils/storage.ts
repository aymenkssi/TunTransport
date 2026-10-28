// Persistent storage: AsyncStorage for app state, SecureStore for secrets (falls back on web).
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

async function get<T>(key: string, fallback: T): Promise<T> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

async function set(key: string, value: unknown): Promise<void> {
  try {
    if (value === null || value === undefined) await AsyncStorage.removeItem(key);
    else await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

async function secureGet(key: string): Promise<string | null> {
  if (Platform.OS === "web") return get<string | null>(key, null);
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function secureSet(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") return set(key, value);
  try {
    await SecureStore.setItemAsync(key, value);
  } catch {}
}

export const storage = { get, set, secureGet, secureSet };
