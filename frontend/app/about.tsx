// About: how sharing works, privacy, and deleting one's data.
import * as Linking from "expo-linking";
import { useMemo, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text } from "react-native";

import { deleteMyData } from "@/src/api/client";
import { stopSharing } from "@/src/sharing/session";
import { Colors, radius, spacing, type, useColors } from "@/src/theme";

const SITE = (process.env.EXPO_PUBLIC_SITE_URL || "").replace(/\/+$/, "");

export default function AboutScreen() {
  const colors = useColors();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [busy, setBusy] = useState(false);

  const remove = async () => {
    setBusy(true);
    try {
      await stopSharing();
      await deleteMyData();
      Alert.alert("Données supprimées", "Votre identifiant anonyme et vos trajets ont été effacés du serveur.");
    } catch {
      Alert.alert("Suppression impossible", "Le serveur ne répond pas. Réessayez plus tard.");
    } finally {
      setBusy(false);
    }
  };

  const confirm = () =>
    Alert.alert("Supprimer mes données ?", "Le partage en cours s’arrête et vos trajets passés sont effacés.", [
      { text: "Annuler", style: "cancel" },
      { text: "Supprimer", style: "destructive", onPress: remove },
    ]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={styles.h}>Comment ça marche</Text>
      <Text style={styles.p}>
        Dans un bus, un métro ou un train, touchez « Je suis dans ce véhicule ». Votre téléphone envoie sa position
        toutes les 5 secondes ; le serveur vérifie qu’elle suit bien la ligne et le sens choisis avant de montrer le
        véhicule aux autres voyageurs. Plusieurs passagers dans le même véhicule le rendent « fiable ».
      </Text>
      <Text style={styles.h}>Confidentialité</Text>
      <Text style={styles.p}>
        • Le partage ne démarre que sur votre demande et s’arrête d’un geste, automatiquement si vous quittez la ligne
        pendant 2 minutes, et au plus tard après 2 heures.{"\n"}
        • Les autres voient un véhicule, jamais une personne.{"\n"}
        • Vos coordonnées GPS ne sont pas enregistrées : le serveur ne garde que la position du véhicule le long de la
        ligne, effacée 5 minutes après la dernière mise à jour.{"\n"}
        • Aucun compte, aucun nom, aucun e-mail : un identifiant anonyme est créé sur votre téléphone.{"\n"}
        • Contre les fausses déclarations, le serveur vérifie que le véhicule avance vraiment sur la ligne (pas à
        pied, pas immobile, pas de position simulée) et tient compte des confirmations et des signalements des
        autres voyageurs.
      </Text>
      {SITE ? (
        <Pressable onPress={() => Linking.openURL(`${SITE}/privacy`)}>
          <Text style={styles.link}>Politique de confidentialité complète</Text>
        </Pressable>
      ) : null}
      <Pressable style={[styles.danger, busy && styles.disabled]} onPress={confirm} disabled={busy}>
        <Text style={styles.dangerText}>Supprimer mes données</Text>
      </Pressable>
      <Text style={styles.small}>
        Lignes, arrêts et horaires : tunismapper.com. Carte et adresses : OpenFreeMap et Nominatim, données © contributeurs OpenStreetMap.
      </Text>
    </ScrollView>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.surface },
    content: { padding: spacing.md, gap: spacing.sm + 4 },
    h: { color: c.onSurface, fontSize: type.lg, fontWeight: "700", marginTop: spacing.sm },
    p: { color: c.onSurface, fontSize: type.base, lineHeight: 21 },
    link: { color: c.info, fontSize: type.base, fontWeight: "600" },
    danger: { alignSelf: "flex-start", marginTop: spacing.md, borderWidth: 1, borderColor: c.error, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 2 },
    dangerText: { color: c.error, fontWeight: "700", fontSize: type.base },
    disabled: { opacity: 0.5 },
    small: { color: c.onSurfaceSecondary, fontSize: type.sm, marginTop: spacing.lg },
  });
