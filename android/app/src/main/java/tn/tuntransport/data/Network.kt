package tn.tuntransport.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import tn.tuntransport.core.LatLon
import tn.tuntransport.core.Shape
import java.time.LocalTime

/** Réseau embarqué dans assets/network.json (généré par tools/import_tunismapper.py). */
@Serializable
data class Network(
    val source: String,
    val generated: String,
    val lines: List<TransitLine>,
)

@Serializable
data class TransitLine(
    val id: String,
    val mode: String,
    @SerialName("short_name") val shortName: String,
    @SerialName("long_name") val longName: String,
    val color: String? = null,
    val operator: String = "",
    @SerialName("shape_source") val shapeSource: String,
    val stops: List<Stop>,
    val directions: List<Direction>,
    /** arrêt → girouette → heures de passage « HH:MM ». */
    val timetable: Map<String, Map<String, List<String>>> = emptyMap(),
) {
    val label: String get() = shortName.ifBlank { longName }

    /** Tracé relevé sur le terrain, ou simple succession d'arrêts reliés en ligne droite. */
    val hasMeasuredShape: Boolean get() = shapeSource == "tunismapper"

    fun stop(id: String): Stop? = stops.firstOrNull { it.id == id }

    /** Prochains passages théoriques à un arrêt, affichés quand personne ne partage. */
    fun nextDepartures(stopId: String, headsign: String, now: LocalTime, count: Int = 2): List<LocalTime> =
        timetable[stopId]?.get(headsign).orEmpty()
            .mapNotNull { runCatching { LocalTime.parse(it) }.getOrNull() }
            .filter { !it.isBefore(now) }
            .take(count)
}

@Serializable
data class Stop(
    val id: String,
    val name: String,
    val lat: Double,
    val lon: Double,
)

@Serializable
data class Direction(
    val headsign: String,
    val shape: List<List<Double>>,
    val stops: List<DirectionStop>,
) {
    val points: List<LatLon> get() = shape.map { LatLon(it[0], it[1]) }

    fun toShape(): Shape = Shape(points)
}

@Serializable
data class DirectionStop(
    val id: String,
    @SerialName("along_m") val alongM: Double,
)

enum class Mode(val key: String, val label: String) {
    METRO("metro", "Métro"),
    BUS("bus", "Bus"),
    RFR("rfr", "RFR"),
    TRAIN("train", "Train");

    companion object {
        fun of(key: String): Mode? = entries.firstOrNull { it.key == key }
    }
}
