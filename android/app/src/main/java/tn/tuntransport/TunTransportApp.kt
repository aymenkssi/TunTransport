package tn.tuntransport

import android.app.Application
import org.maplibre.android.MapLibre

class TunTransportApp : Application() {
    override fun onCreate() {
        super.onCreate()
        MapLibre.getInstance(this)
    }
}
