// Map page rendered in a WebView (native) or an iframe (web): MapLibre GL JS with the free
// OpenFreeMap tiles (OpenStreetMap data, no API key). It receives MapData as JSON messages and
// sends back {type: "stop", id}, {type: "vehicle", index} or {type: "map", lat, lon} when tapped.
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
  paths?: { coords: [number, number][]; color: string; dashed: boolean }[]; // itinerary legs
  markers?: { lat: number; lon: number; label: string; color: string }[]; // itinerary start and end
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
  ["route", "stops", "vehicles", "me", "paths", "markers"].forEach(function (id) { map.addSource(id, { type: "geojson", data: fc([]) }); });
  map.addLayer({ id: "paths-casing", type: "line", source: "paths", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-width": 9, "line-color": "#ffffff" }, filter: ["!", ["get", "dashed"]] });
  map.addLayer({ id: "paths", type: "line", source: "paths", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-width": 6, "line-color": ["get", "color"] }, filter: ["!", ["get", "dashed"]] });
  map.addLayer({ id: "paths-dashed", type: "line", source: "paths", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-width": 5, "line-color": ["get", "color"], "line-dasharray": [1, 1.6] }, filter: ["get", "dashed"] });
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
  map.addLayer({ id: "markers", type: "circle", source: "markers", paint: {
    "circle-radius": 13, "circle-color": ["get", "color"], "circle-stroke-width": 3, "circle-stroke-color": "#ffffff" } });
  map.addLayer({ id: "markers-label", type: "symbol", source: "markers", layout: {
    "text-field": ["get", "label"], "text-size": 12, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true, "text-ignore-placement": true },
    paint: { "text-color": "#ffffff" } });
  map.on("click", function (e) {
    var hit = map.queryRenderedFeatures(e.point, { layers: ["vehicles", "stops"] })[0];
    if (!hit) send({ type: "map", lat: e.lngLat.lat, lon: e.lngLat.lng });
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
  var paths = d.paths || [], markers = d.markers || [];
  map.getSource("paths").setData(fc(paths.map(function (p) {
    return { type: "Feature", properties: { color: p.color, dashed: p.dashed }, geometry: { type: "LineString", coordinates: p.coords.map(function (c) { return [c[1], c[0]]; }) } };
  })));
  map.getSource("markers").setData(fc(markers.map(function (m) { return point(m.lat, m.lon, { label: m.label, color: m.color }); })));
  map.setPaintProperty("route", "line-color", d.color);
  map.setPaintProperty("route", "line-dasharray", d.dashed ? [1.5, 1.5] : [1, 0]);
  map.setPaintProperty("stops", "circle-stroke-color", d.color);
  var pts = d.shape.slice();
  paths.forEach(function (p) { pts = pts.concat(p.coords); });
  markers.forEach(function (m) { pts.push([m.lat, m.lon]); });
  if (d.fitKey !== lastFit && pts.length > 1) {
    lastFit = d.fitKey;
    var b = new maplibregl.LngLatBounds();
    pts.forEach(function (p) { b.extend([p[1], p[0]]); });
    // The map may just have been resized (expanded/collapsed): let the WebView settle first.
    setTimeout(function () { map.resize(); map.fitBounds(b, { padding: 50, duration: 600, maxZoom: 16 }); }, 150);
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
