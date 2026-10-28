package tn.tuntransport.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** Vérifie que le réseau généré par tools/import_tunismapper.py se lit dans l'application. */
class NetworkAssetTest {
    @Test
    fun generatedNetworkDecodes() {
        val file = File("src/main/assets/network.json")
        assumeTrue("network.json non généré", file.exists())
        val network = Json { ignoreUnknownKeys = true }.decodeFromString<Network>(file.readText())

        assertTrue(network.lines.isNotEmpty())
        for (line in network.lines) {
            assertTrue("ligne ${line.id} : deux sens attendus", line.directions.size == 2)
            line.directions.forEach { direction ->
                assertTrue("ligne ${line.id} : tracé vide", direction.shape.size >= 2)
                direction.toShape()
                direction.stops.forEach { assertTrue(line.stop(it.id) != null) }
            }
            assertTrue("ligne ${line.id} : mode inconnu", Mode.of(line.mode) != null)
        }
    }
}
