package tn.tuntransport.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mêmes scénarios que prototype/tests/test_core.py. */
class LineMatcherTest {
    private val lat = 36.80
    private val metersPerDegLon = 89_150.0
    private val east = listOf(LatLon(lat, 10.15), LatLon(lat, 10.17), LatLon(lat, 10.20))
    private val forward = Shape(east)
    private val backward = Shape(east.reversed())

    private fun trace(startLon: Double, speedMps: Double, latitude: Double = lat, accuracyM: Double = 10.0) =
        (0 until 6).map { i ->
            LineMatcher.GpsFix(1000.0 + i * 10, LatLon(latitude, startLon + speedMps * i * 10 / metersPerDegLon), accuracyM)
        }

    @Test
    fun acceptsPassengerOnDeclaredLine() {
        val result = LineMatcher.match(trace(10.16, 8.0), forward, LineMatcher.MAX_OFFSET_MEASURED_M)
        assertTrue(result is LineMatcher.Result.OnRoute)
        assertEquals(8.0, (result as LineMatcher.Result.OnRoute).speedMps, 0.3)
    }

    @Test
    fun rejectsWrongDirection() {
        val result = LineMatcher.match(trace(10.16, 8.0), backward, LineMatcher.MAX_OFFSET_MEASURED_M)
        assertEquals(LineMatcher.Result.Rejected(LineMatcher.Reason.WRONG_DIRECTION), result)
    }

    @Test
    fun rejectsPassengerOffRoute() {
        val result = LineMatcher.match(trace(10.16, 8.0, latitude = lat + 0.002), forward, LineMatcher.MAX_OFFSET_MEASURED_M)
        assertEquals(LineMatcher.Result.Rejected(LineMatcher.Reason.OFF_ROUTE), result)
    }

    @Test
    fun widerToleranceForStopsOnlyShapes() {
        // ~110 m du tracé : refusé pour un tracé relevé, accepté pour des arrêts reliés en ligne droite.
        val fixes = trace(10.16, 8.0, latitude = lat + 0.001)
        assertTrue(LineMatcher.match(fixes, forward, LineMatcher.MAX_OFFSET_MEASURED_M) is LineMatcher.Result.Rejected)
        assertTrue(LineMatcher.match(fixes, forward, LineMatcher.MAX_OFFSET_STOPS_ONLY_M) is LineMatcher.Result.OnRoute)
    }

    @Test
    fun ignoresImpreciseFixes() {
        val result = LineMatcher.match(trace(10.16, 8.0, accuracyM = 200.0), forward, LineMatcher.MAX_OFFSET_MEASURED_M)
        assertEquals(LineMatcher.Result.Rejected(LineMatcher.Reason.TOO_SHORT), result)
    }
}
