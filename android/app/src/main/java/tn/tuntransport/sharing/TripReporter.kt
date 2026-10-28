package tn.tuntransport.sharing

import android.util.Log

/** Position validée d'un passager, telle qu'elle sera envoyée au serveur.
 * Pas de coordonnées brutes : seulement la position le long du tracé. */
data class PositionUpdate(
    /** Identifiant aléatoire propre à ce trajet, sans lien avec le compte. */
    val tripId: String,
    val lineId: String,
    val directionIndex: Int,
    val alongM: Double,
    val speedMps: Double,
    val timeMs: Long,
)

interface TripReporter {
    fun report(update: PositionUpdate)
    fun end(tripId: String)
}

/** En attendant le serveur : journalise seulement. */
class LogTripReporter : TripReporter {
    override fun report(update: PositionUpdate) {
        Log.d(TAG, "position $update")
    }

    override fun end(tripId: String) {
        Log.d(TAG, "fin du trajet $tripId")
    }

    private companion object {
        const val TAG = "TripReporter"
    }
}
