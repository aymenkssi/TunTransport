// Map page rendered in a WebView (native) or an iframe (web): MapLibre GL JS with the free
// OpenFreeMap tiles (OpenStreetMap data, no API key). It receives MapData as JSON messages and
// sends {type: "stop", id} back when a stop is tapped.
import type { Vehicle } from "@/src/api/network";

export type MapData = {
  fitKey: string; // the camera re-frames the line only when this changes
  color: string;
  dashed: boolean;
  shape: [number, number][]; // [lat, lon]
  stops: { id: string; name: string; lat: number; lon: number; selected: boolean }[];
  vehicles: Pick<Vehicle, "lat" | "lon" | "status" | "confirmations">[];
};

export const MAP_HTML = `<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>html,body,#map{margin:0;height:100%;width:100%;background:#e5e7eb}</style>
</head><body><div id="map"></div><script>
var STATUS = { "fiable": "#047857", "probable": "#1D4ED8", "obsolète": "#9CA3AF" };
var map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/liberty",
  center: [10.1815, 36.8065],
  zoom: 11,
  attributionControl: { compact: true }
});
var ready = false, pending = null, lastFit = "";
function fc(features) { return { type: "FeatureCollection", features: features }; }
function point(lat, lon, props) { return { type: "Feature", properties: props || {}, geometry: { type: "Point", coordinates: [lon, lat] } }; }
function send(msg) {
  var s = JSON.stringify(msg);
  if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(s); else window.parent.postMessage(s, "*");
}
map.on("style.load", function () {
  map.addSource("route", { type: "geojson", data: fc([]) });
  map.addSource("stops", { type: "geojson", data: fc([]) });
  map.addSource("vehicles", { type: "geojson", data: fc([]) });
  map.addLayer({ id: "route", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-width": 5, "line-color": "#E70013" } });
  map.addLayer({ id: "stops", type: "circle", source: "stops", paint: {
    "circle-radius": ["case", ["get", "selected"], 8, 5], "circle-color": "#ffffff",
    "circle-stroke-width": ["case", ["get", "selected"], 4, 2.5], "circle-stroke-color": "#E70013" } });
  map.addLayer({ id: "vehicles", type: "circle", source: "vehicles", paint: {
    "circle-radius": 11, "circle-color": ["get", "fill"], "circle-stroke-width": 3, "circle-stroke-color": "#ffffff" } });
  map.addLayer({ id: "vehicles-count", type: "symbol", source: "vehicles", layout: {
    "text-field": ["to-string", ["get", "confirmations"]], "text-size": 12, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true },
    paint: { "text-color": "#ffffff" } });
  map.on("click", "stops", function (e) { if (e.features && e.features[0]) send({ type: "stop", id: e.features[0].properties.id }); });
  map.on("mouseenter", "stops", function () { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", "stops", function () { map.getCanvas().style.cursor = ""; });
  ready = true;
  if (pending) apply(pending);
});
function apply(d) {
  if (!ready) { pending = d; return; }
  var line = d.shape.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: d.shape.map(function (p) { return [p[1], p[0]]; }) } }] : [];
  map.getSource("route").setData(fc(line));
  map.getSource("stops").setData(fc(d.stops.map(function (s) { return point(s.lat, s.lon, { id: s.id, name: s.name, selected: s.selected }); })));
  map.getSource("vehicles").setData(fc(d.vehicles.map(function (v) { return point(v.lat, v.lon, { fill: STATUS[v.status] || "#1D4ED8", confirmations: v.confirmations }); })));
  map.setPaintProperty("route", "line-color", d.color);
  map.setPaintProperty("route", "line-dasharray", d.dashed ? [1.5, 1.5] : [1, 0]);
  map.setPaintProperty("stops", "circle-stroke-color", d.color);
  if (d.fitKey !== lastFit && d.shape.length > 1) {
    lastFit = d.fitKey;
    var b = new maplibregl.LngLatBounds();
    d.shape.forEach(function (p) { b.extend([p[1], p[0]]); });
    map.fitBounds(b, { padding: 40, duration: 0 });
  }
}
function onMessage(e) { try { var d = JSON.parse(e.data); if (d && d.shape) apply(d); } catch (err) {} }
window.addEventListener("message", onMessage);
document.addEventListener("message", onMessage);
send({ type: "ready" });
</script></body></html>`;
