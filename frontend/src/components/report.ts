// Shared "this vehicle does not exist" flow: confirmation, then a thank-you or the reason it failed.
import { Alert } from "react-native";

import { ApiError } from "@/src/api/client";
import { reportVehicle, Vehicle } from "@/src/api/network";

const ERRORS: Record<number, string> = {
  404: "Ce véhicule n’est plus à cet endroit : la carte s’est peut-être mise à jour.",
  409: "Vous partagez vous-même ce véhicule.",
  429: "Vous avez atteint la limite de signalements pour aujourd’hui.",
};

export function confirmReport(lineId: string, vehicle: Pick<Vehicle, "direction" | "lat" | "lon">, onDone?: () => void) {
  Alert.alert(
    "Ce véhicule n’existe pas ?",
    "Signalez-le si vous êtes à l’endroit indiqué et qu’aucun véhicule de cette ligne n’y passe. Plusieurs signalements le retirent de la carte.",
    [
      { text: "Annuler", style: "cancel" },
      {
        text: "Signaler",
        style: "destructive",
        onPress: async () => {
          try {
            await reportVehicle(lineId, vehicle);
            Alert.alert("Merci", "Votre signalement aide à garder la carte fiable.");
            onDone?.();
          } catch (e) {
            const status = e instanceof ApiError ? e.status : 0;
            Alert.alert("Signalement impossible", ERRORS[status] ?? "Le serveur ne répond pas. Réessayez plus tard.");
          }
        },
      },
    ],
  );
}
