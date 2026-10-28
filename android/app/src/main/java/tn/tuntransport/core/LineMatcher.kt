package tn.tuntransport.core

/** Vérifie qu'une trace GPS est compatible avec le tracé déclaré (ligne + sens).
 * Même règles que prototype/tuntransport_core/line_matching.py. */
object LineMatcher {
    const val MAX_ACCURACY_M = 50.0
    /** Écart toléré au tracé quand il a été relevé sur le terrain. */
    const val MAX_OFFSET_MEASURED_M = 40.0
    /** Écart toléré quand le tracé n'est qu'une suite d'arrêts reliés en ligne droite. */
    const val MAX_OFFSET_STOPS_ONLY_M = 150.0
    const val MIN_ON_ROUTE_RATIO = 0.8
    const val MIN_FIXES = 3
    const val MIN_DURATION_S = 20.0
    const val BACKWARD_TOLERANCE_M = 30.0
    const val MAX_SPEED_MPS = 33.0

    data class GpsFix(val timeS: Double, val position: LatLon, val accuracyM: Double = 10.0)

    sealed interface Result {
        data class OnRoute(val alongM: Double, val speedMps: Double, val meanOffsetM: Double) : Result
        data class Rejected(val reason: Reason) : Result
    }

    enum class Reason(val label: String) {
        TOO_SHORT("trace trop courte"),
        OFF_ROUTE("hors du tracé de la ligne"),
        WRONG_DIRECTION("mauvais sens de circulation"),
        IMPLAUSIBLE_SPEED("vitesse incohérente"),
    }

    fun match(fixes: List<GpsFix>, shape: Shape, maxOffsetM: Double): Result {
        val usable = fixes.filter { it.accuracyM <= MAX_ACCURACY_M }.sortedBy { it.timeS }
        if (usable.size < MIN_FIXES || usable.last().timeS - usable.first().timeS < MIN_DURATION_S) {
            return Result.Rejected(Reason.TOO_SHORT)
        }

        val projections = usable.map { shape.project(it.position) }
        val onRoute = projections.zip(usable).count { (p, f) -> p.offsetM <= maxOf(maxOffsetM, f.accuracyM) }
        if (onRoute.toDouble() / usable.size < MIN_ON_ROUTE_RATIO) return Result.Rejected(Reason.OFF_ROUTE)

        val progress = projections.last().alongM - projections.first().alongM
        if (progress < -BACKWARD_TOLERANCE_M) return Result.Rejected(Reason.WRONG_DIRECTION)

        val speed = progress.coerceAtLeast(0.0) / (usable.last().timeS - usable.first().timeS)
        if (speed > MAX_SPEED_MPS) return Result.Rejected(Reason.IMPLAUSIBLE_SPEED)

        return Result.OnRoute(projections.last().alongM, speed, projections.map { it.offsetM }.average())
    }
}
