package tn.tuntransport.ui

import android.graphics.Color
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineDasharray
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.LineString
import org.maplibre.geojson.Point
import tn.tuntransport.data.TransitLine

/** Fond OpenStreetMap servi par OpenFreeMap : gratuit, sans clé d'API. */
private const val STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"
private val TUNIS = LatLng(36.8065, 10.1815)
private const val ROUTE_SOURCE = "route"
private const val STOPS_SOURCE = "stops"
private const val ROUTE_LAYER = "route-line"
private const val STOPS_LAYER = "route-stops"

@Composable
fun TransitMap(line: TransitLine?, directionIndex: Int, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val mapView = remember { MapView(context).apply { onCreate(null) } }
    var map by remember { mutableStateOf<MapLibreMap?>(null) }
    var style by remember { mutableStateOf<Style?>(null) }

    DisposableEffect(lifecycle, mapView) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            mapView.onDestroy()
        }
    }

    LaunchedEffect(mapView) {
        mapView.getMapAsync { loaded ->
            loaded.cameraPosition = CameraPosition.Builder().target(TUNIS).zoom(11.0).build()
            loaded.setStyle(Style.Builder().fromUri(STYLE_URL)) { loadedStyle ->
                loadedStyle.addSource(GeoJsonSource(ROUTE_SOURCE))
                loadedStyle.addSource(GeoJsonSource(STOPS_SOURCE))
                loadedStyle.addLayer(
                    LineLayer(ROUTE_LAYER, ROUTE_SOURCE).withProperties(
                        lineWidth(5f),
                        lineCap(Property.LINE_CAP_ROUND),
                        lineJoin(Property.LINE_JOIN_ROUND),
                    ),
                )
                loadedStyle.addLayer(
                    CircleLayer(STOPS_LAYER, STOPS_SOURCE).withProperties(
                        circleRadius(5f),
                        circleColor(Color.WHITE),
                        circleStrokeWidth(2.5f),
                    ),
                )
                map = loaded
                style = loadedStyle
            }
        }
    }

    LaunchedEffect(line, directionIndex, style) {
        val currentStyle = style ?: return@LaunchedEffect
        val currentMap = map ?: return@LaunchedEffect
        val direction = line?.directions?.getOrNull(directionIndex)
        val points = direction?.points.orEmpty()
        val stops = direction?.stops.orEmpty().mapNotNull { line?.stop(it.id) }
        val color = line?.color?.let(Color::parseColor) ?: Color.DKGRAY

        currentStyle.getSourceAs<GeoJsonSource>(ROUTE_SOURCE)?.setGeoJson(
            FeatureCollection.fromFeatures(
                if (points.size < 2) emptyList()
                else listOf(Feature.fromGeometry(LineString.fromLngLats(points.map { Point.fromLngLat(it.lon, it.lat) }))),
            ),
        )
        currentStyle.getSourceAs<GeoJsonSource>(STOPS_SOURCE)?.setGeoJson(
            FeatureCollection.fromFeatures(stops.map { stop ->
                Feature.fromGeometry(Point.fromLngLat(stop.lon, stop.lat)).also { it.addStringProperty("name", stop.name) }
            }),
        )
        // Tracé approximatif (arrêts reliés en ligne droite) : affiché en pointillés.
        currentStyle.getLayer(ROUTE_LAYER)?.setProperties(
            lineColor(color),
            lineDasharray(if (line?.hasMeasuredShape == false) arrayOf(1.5f, 1.5f) else arrayOf(1f, 0f)),
        )
        currentStyle.getLayer(STOPS_LAYER)?.setProperties(circleStrokeColor(color))

        if (points.size >= 2) {
            val bounds = LatLngBounds.Builder().includes(points.map { LatLng(it.lat, it.lon) }).build()
            currentMap.easeCamera(CameraUpdateFactory.newLatLngBounds(bounds, 96), 600)
        }
    }

    AndroidView(factory = { mapView }, modifier = modifier)
}
