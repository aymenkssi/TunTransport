package tn.tuntransport.sharing

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.location.Location
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import tn.tuntransport.R
import tn.tuntransport.core.LatLon
import tn.tuntransport.core.LineMatcher
import tn.tuntransport.core.Shape
import tn.tuntransport.data.NetworkRepository
import tn.tuntransport.ui.MainActivity
import java.util.UUID

/** Service au premier plan qui suit le passager pendant son trajet.
 * La position n'est transmise que lorsqu'elle est validée sur la ligne déclarée. */
class ShareService : Service() {
    private lateinit var locationClient: FusedLocationProviderClient
    private val reporter: TripReporter = LogTripReporter()
    private val fixes = ArrayDeque<LineMatcher.GpsFix>()

    private var active: ShareSession.State.Active? = null
    private var shape: Shape? = null
    private var maxOffsetM = LineMatcher.MAX_OFFSET_MEASURED_M
    private var tripId = ""
    private var startedAtMs = 0L
    private var lastOnRouteMs = 0L

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.locations.forEach(::onLocation)
        }
    }

    override fun onCreate() {
        super.onCreate()
        locationClient = LocationServices.getFusedLocationProviderClient(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSharing()
            return START_NOT_STICKY
        }
        val line = intent?.getStringExtra(EXTRA_LINE_ID)?.let { NetworkRepository.line(this, it) }
        val directionIndex = intent?.getIntExtra(EXTRA_DIRECTION, 0) ?: 0
        val direction = line?.directions?.getOrNull(directionIndex)
        if (line == null || direction == null) {
            stopSelf()
            return START_NOT_STICKY
        }

        val state = ShareSession.State.Active(
            line.id, directionIndex, line.label, direction.headsign, ShareSession.Status.Checking,
        )
        ServiceCompat.startForeground(
            this, NOTIFICATION_ID, notification(state), ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
        )
        active?.let { reporter.end(tripId) }
        active = state
        shape = direction.toShape()
        maxOffsetM = if (line.hasMeasuredShape) LineMatcher.MAX_OFFSET_MEASURED_M else LineMatcher.MAX_OFFSET_STOPS_ONLY_M
        tripId = UUID.randomUUID().toString()
        startedAtMs = System.currentTimeMillis()
        lastOnRouteMs = startedAtMs
        fixes.clear()
        ShareSession.update(state)
        requestLocationUpdates()
        return START_NOT_STICKY
    }

    private fun requestLocationUpdates() {
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, UPDATE_INTERVAL_MS)
            .setMinUpdateIntervalMillis(UPDATE_INTERVAL_MS / 2)
            .build()
        try {
            locationClient.requestLocationUpdates(request, callback, Looper.getMainLooper())
        } catch (_: SecurityException) {
            stopSharing() // permission retirée entre-temps
        }
    }

    private fun onLocation(location: Location) {
        val current = active ?: return
        val shape = shape ?: return
        val now = location.time
        fixes.addLast(
            LineMatcher.GpsFix(now / 1000.0, LatLon(location.latitude, location.longitude), location.accuracy.toDouble()),
        )
        while (fixes.isNotEmpty() && now / 1000.0 - fixes.first().timeS > TRACE_WINDOW_S) fixes.removeFirst()

        val status = when (val result = LineMatcher.match(fixes, shape, maxOffsetM)) {
            is LineMatcher.Result.OnRoute -> {
                lastOnRouteMs = now
                reporter.report(
                    PositionUpdate(tripId, current.lineId, current.directionIndex, result.alongM, result.speedMps, now),
                )
                ShareSession.Status.OnRoute(result.alongM, result.speedMps)
            }
            is LineMatcher.Result.Rejected ->
                if (result.reason == LineMatcher.Reason.TOO_SHORT) ShareSession.Status.Checking
                else ShareSession.Status.Rejected(result.reason.label)
        }
        val updated = current.copy(status = status)
        active = updated
        ShareSession.update(updated)

        // Arrêt automatique : le passager a quitté la ligne, ou a oublié d'arrêter.
        if (now - lastOnRouteMs > AUTO_STOP_OFF_ROUTE_MS || now - startedAtMs > MAX_TRIP_MS) stopSharing()
    }

    private fun stopSharing() {
        locationClient.removeLocationUpdates(callback)
        if (active != null) reporter.end(tripId)
        active = null
        fixes.clear()
        ShareSession.update(ShareSession.State.Idle)
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        if (active != null) stopSharing()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(state: ShareSession.State.Active): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, getString(R.string.share_channel), NotificationManager.IMPORTANCE_LOW),
        )
        val stop = PendingIntent.getService(
            this, 0, Intent(this, ShareService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_share)
            .setContentTitle(getString(R.string.share_notification_title))
            .setContentText(getString(R.string.share_notification_text, state.lineLabel, state.headsign))
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(0, getString(R.string.share_stop), stop)
            .build()
    }

    companion object {
        private const val ACTION_STOP = "tn.tuntransport.action.STOP_SHARING"
        private const val EXTRA_LINE_ID = "line_id"
        private const val EXTRA_DIRECTION = "direction"
        private const val CHANNEL_ID = "sharing"
        private const val NOTIFICATION_ID = 1
        private const val UPDATE_INTERVAL_MS = 5_000L
        private const val TRACE_WINDOW_S = 60.0
        private const val AUTO_STOP_OFF_ROUTE_MS = 2 * 60_000L
        private const val MAX_TRIP_MS = 2 * 60 * 60_000L

        fun startIntent(context: Context, lineId: String, directionIndex: Int): Intent =
            Intent(context, ShareService::class.java)
                .putExtra(EXTRA_LINE_ID, lineId)
                .putExtra(EXTRA_DIRECTION, directionIndex)

        fun stopIntent(context: Context): Intent =
            Intent(context, ShareService::class.java).setAction(ACTION_STOP)
    }
}
