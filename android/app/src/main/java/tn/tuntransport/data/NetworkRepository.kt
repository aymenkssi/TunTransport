package tn.tuntransport.data

import android.content.Context
import kotlinx.serialization.json.Json
import java.io.FileNotFoundException

object NetworkRepository {
    private val json = Json { ignoreUnknownKeys = true }

    @Volatile
    private var cached: Network? = null

    /** Charge le réseau embarqué ; null si l'asset n'a pas été généré. */
    fun load(context: Context): Network? {
        cached?.let { return it }
        return synchronized(this) {
            cached ?: try {
                context.assets.open("network.json").bufferedReader().use { reader ->
                    json.decodeFromString<Network>(reader.readText())
                }.also { cached = it }
            } catch (_: FileNotFoundException) {
                null
            }
        }
    }

    fun line(context: Context, id: String): TransitLine? = load(context)?.lines?.firstOrNull { it.id == id }
}
