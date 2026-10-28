package tn.tuntransport.core

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import kotlin.math.sqrt

const val EARTH_RADIUS_M = 6_371_000.0

data class LatLon(val lat: Double, val lon: Double)

fun haversineM(a: LatLon, b: LatLon): Double {
    val lat1 = Math.toRadians(a.lat)
    val lat2 = Math.toRadians(b.lat)
    val dLat = lat2 - lat1
    val dLon = Math.toRadians(b.lon - a.lon)
    val h = sin(dLat / 2).let { it * it } + cos(lat1) * cos(lat2) * sin(dLon / 2).let { it * it }
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))
}

data class Projection(
    /** Abscisse curviligne depuis le terminus de départ. */
    val alongM: Double,
    /** Distance latérale entre le point et le tracé. */
    val offsetM: Double,
)

/** Tracé d'une ligne dans un sens. Même algorithme que prototype/tuntransport_core/geo.py. */
class Shape(val points: List<LatLon>) {
    init {
        require(points.size >= 2) { "un tracé doit contenir au moins deux points" }
    }

    private val cumulativeM: DoubleArray = DoubleArray(points.size).also { cum ->
        for (i in 1 until points.size) cum[i] = cum[i - 1] + haversineM(points[i - 1], points[i])
    }

    val lengthM: Double get() = cumulativeM.last()

    /** Projection équirectangulaire locale, suffisante à l'échelle d'une ville. */
    fun project(p: LatLon): Projection {
        val cosLat = cos(Math.toRadians(p.lat))
        fun x(q: LatLon) = Math.toRadians(q.lon - p.lon) * cosLat * EARTH_RADIUS_M
        fun y(q: LatLon) = Math.toRadians(q.lat - p.lat) * EARTH_RADIUS_M

        var best: Projection? = null
        for (i in 0 until points.size - 1) {
            val ax = x(points[i]); val ay = y(points[i])
            val dx = x(points[i + 1]) - ax; val dy = y(points[i + 1]) - ay
            val seg2 = dx * dx + dy * dy
            val t = if (seg2 == 0.0) 0.0 else (-(ax * dx + ay * dy) / seg2).coerceIn(0.0, 1.0)
            val offset = hypot(ax + t * dx, ay + t * dy)
            if (best == null || offset < best.offsetM) {
                best = Projection(cumulativeM[i] + t * (cumulativeM[i + 1] - cumulativeM[i]), offset)
            }
        }
        return best!!
    }
}
