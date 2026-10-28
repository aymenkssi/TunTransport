package tn.tuntransport.data

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalTime

class TimetableTest {
    private val line = TransitLine(
        id = "19", mode = "rfr", shortName = "A", longName = "Tunis Ville-Erriadh", shapeSource = "tunismapper",
        stops = emptyList(), directions = emptyList(),
        timetable = mapOf("202" to mapOf("Erriadh" to listOf("05:25", "06:10", "07:00"), "Tunis Ville" to listOf("05:12"))),
    )

    @Test
    fun nextDeparturesForHeadsign() {
        assertEquals(
            listOf(LocalTime.of(6, 10), LocalTime.of(7, 0)),
            line.nextDepartures("202", "Erriadh", LocalTime.of(6, 0)),
        )
    }

    @Test
    fun noDepartureAfterLastService() {
        assertEquals(emptyList<LocalTime>(), line.nextDepartures("202", "Tunis Ville", LocalTime.of(23, 0)))
    }
}
