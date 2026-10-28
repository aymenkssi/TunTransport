// Map page rendered in a WebView (native) or an iframe (web): MapLibre GL JS with the free
// OpenFreeMap tiles (OpenStreetMap data, no API key). It receives MapData as JSON messages and
// sends back {type: "stop", id}, {type: "vehicle", index} or {type: "map"} when tapped.
import type { Vehicle } from "@/src/api/network";

export type MapVehicle = Pick<Vehicle, "lat" | "lon" | "status" | "confirmations"> & {
  color?: string | null; // line colour on the network map; reliability colour otherwise
  label?: string; // line number on the network map; number of passengers otherwise
  selected?: boolean;
};

export type MapData = {
  fitKey: string; // the camera re-frames the line only when this changes
  color: string;
  dashed: boolean;
  shape: [number, number][]; // [lat, lon]
  stops: { id: string; name: string; lat: number; lon: number; selected: boolean }[];
  vehicles: MapVehicle[];
  me?: { lat: number; lon: number } | null;
  center?: { key: string; lat: number; lon: number; zoom: number } | null; // flies there when key changes
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
var ready = false, pending = null, lastFit = "", lastCenter = "";
function fc(features) { return { type: "FeatureCollection", features: features }; }
function point(lat, lon, props) { return { type: "Feature", properties: props || {}, geometry: { type: "Point", coordinates: [lon, lat] } }; }
function send(msg) {
  var s = JSON.stringify(msg);
  if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(s); else window.parent.postMessage(s, "*");
}
// "style.load" rather than "load": layers appear as soon as the style is ready, even if tiles are slow.
map.on("style.load", function () {
  ["route", "stops", "vehicles", "me"].forEach(function (id) { map.addSource(id, { type: "geojson", data: fc([]) }); });
  map.addLayer({ id: "route", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-width": 5, "line-color": "#E70013" } });
  map.addLayer({ id: "stops", type: "circle", source: "stops", paint: {
    "circle-radius": ["case", ["get", "selected"], 8, 5], "circle-color": "#ffffff",
    "circle-stroke-width": ["case", ["get", "selected"], 4, 2.5], "circle-stroke-color": "#E70013" } });
  map.addLayer({ id: "me", type: "circle", source: "me", paint: {
    "circle-radius": 8, "circle-color": "#2563EB", "circle-stroke-width": 3, "circle-stroke-color": "#ffffff" } });
  map.addLayer({ id: "vehicles", type: "circle", source: "vehicles", paint: {
    "circle-radius": ["case", ["get", "selected"], 16, 13], "circle-color": ["get", "fill"], "circle-opacity": ["get", "opacity"],
    "circle-stroke-width": ["case", ["get", "selected"], 4, 3], "circle-stroke-color": "#ffffff" } });
  map.addLayer({ id: "vehicles-label", type: "symbol", source: "vehicles", layout: {
    "text-field": ["get", "label"], "text-size": 11, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true, "text-ignore-placement": true },
    paint: { "text-color": ["get", "ink"] } });
  map.on("click", function (e) {
    var hit = map.queryRenderedFeatures(e.point, { layers: ["vehicles", "stops"] })[0];
    if (!hit) send({ type: "map" });
    else if (hit.layer.id === "vehicles") send({ type: "vehicle", index: hit.properties.index });
    else send({ type: "stop", id: hit.properties.id });
  });
  ["vehicles", "stops"].forEach(function (id) {
    map.on("mouseenter", id, function () { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", id, function () { map.getCanvas().style.cursor = ""; });
  });
  ready = true;
  if (pending) apply(pending);
});
function ink(hex) {
  var n = parseInt(hex.slice(1), 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 170 ? "#111827" : "#ffffff";
}
function apply(d) {
  if (!ready) { pending = d; return; }
  var line = d.shape.length > 1 ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: d.shape.map(function (p) { return [p[1], p[0]]; }) } }] : [];
  map.getSource("route").setData(fc(line));
  map.getSource("stops").setData(fc(d.stops.map(function (s) { return point(s.lat, s.lon, { id: s.id, name: s.name, selected: s.selected }); })));
  map.getSource("vehicles").setData(fc(d.vehicles.map(function (v, i) {
    var fill = v.color || STATUS[v.status] || "#1D4ED8";
    return point(v.lat, v.lon, { index: i, fill: fill, ink: ink(fill), selected: !!v.selected,
      opacity: v.status === "obsolète" ? 0.45 : 1, label: v.label != null ? String(v.label) : String(v.confirmations) });
  })));
  map.getSource("me").setData(fc(d.me ? [point(d.me.lat, d.me.lon)] : []));
  map.setPaintProperty("route", "line-color", d.color);
  map.setPaintProperty("route", "line-dasharray", d.dashed ? [1.5, 1.5] : [1, 0]);
  map.setPaintProperty("stops", "circle-stroke-color", d.color);
  if (d.fitKey !== lastFit && d.shape.length > 1) {
    lastFit = d.fitKey;
    var b = new maplibregl.LngLatBounds();
    d.shape.forEach(function (p) { b.extend([p[1], p[0]]); });
    map.fitBounds(b, { padding: 40, duration: 0 });
  }
  if (d.center && d.center.key !== lastCenter) {
    lastCenter = d.center.key;
    map.flyTo({ center: [d.center.lon, d.center.lat], zoom: d.center.zoom, duration: 800 });
  }
}
function onMessage(e) { try { var d = JSON.parse(e.data); if (d && d.shape) apply(d); } catch (err) {} }
window.addEventListener("message", onMessage);
document.addEventListener("message", onMessage);
send({ type: "ready" });
</script></body></html>`;
