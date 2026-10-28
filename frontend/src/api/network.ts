// Lines, live vehicles and trips.
import { authed, request } from "@/src/api/client";

export type Mode = "metro" | "bus" | "rfr" | "train";

export type LineSummary = {
  id: string;
  mode: Mode;
  short_name: string;
  long_name: string;
  color: string | null;
  operator: string;
};

export type Stop = { id: string; name: string; lat: number; lon: number };
export type DirectionStop = { id: string; along_m: number };
export type Direction = { headsign: string; shape: [number, number][]; stops: DirectionStop[] };

export type Line = LineSummary & {
  shape_source: "tunismapper" | "stops";
  stops: Stop[];
  directions: Direction[];
  timetable: Record<string, Record<string, string[]>>;
};

export type Vehicle = {
  direction: number;
  headsign: string;
  lat: number;
  lon: number;
  along_m: number;
  speed_mps: number;
  confirmations: number;
  age_s: number;
  reliability: number;
  status: "fiable" | "probable" | "obsolète";
  eta_s: number | null;
};

export type LiveVehicle = Vehicle & {
  line_id: string;
  line_label: string;
  long_name: string;
  mode: Mode;
  color: string | null;
};

// `mocked`: Android says the position comes from a fake-GPS app; the server then stops the trip.
export type Fix = { t: number; lat: number; lon: number; accuracy: number; mocked: boolean };

export type PositionResult = {
  status: "checking" | "on_route" | "rejected";
  reason: string | null;
  along_m: number | null;
  speed_mps: number | null;
};

export type TripStarted = { id: string; line_id: string; direction: number; headsign: string };

export const lineLabel = (line: LineSummary) => line.short_name || line.long_name;

export const getLines = () => request<LineSummary[]>("/lines");
export const getLine = (id: string) => request<Line>(`/lines/${encodeURIComponent(id)}`);
export const getLiveVehicles = () => request<LiveVehicle[]>("/vehicles/live");
export const getLive = () => request<Record<string, number>>("/live");

export const getVehicles = (lineId: string, stopId?: string) =>
  request<Vehicle[]>(`/lines/${encodeURIComponent(lineId)}/vehicles${stopId ? `?stop_id=${encodeURIComponent(stopId)}` : ""}`);

export const startTrip = (lineId: string, direction: number) =>
  authed<TripStarted>("/trips", { method: "POST", body: JSON.stringify({ line_id: lineId, direction }) });

export const postPositions = (tripId: string, fixes: Fix[]) =>
  authed<PositionResult>(`/trips/${tripId}/positions`, { method: "POST", body: JSON.stringify({ fixes }) });

/** "This vehicle does not exist": several reports hide it and lower its contributors' reputation. */
export const reportVehicle = (lineId: string, v: Pick<Vehicle, "direction" | "lat" | "lon">) =>
  authed<{ ok: boolean }>("/vehicles/report", {
    method: "POST",
    body: JSON.stringify({ line_id: lineId, direction: v.direction, lat: v.lat, lon: v.lon }),
  });

export const endTrip = (tripId: string) => authed<{ ok: boolean }>(`/trips/${tripId}/end`, { method: "POST" });

export type StopHit = { id: string; name: string; lat: number; lon: number; lines: LineSummary[] };

export type PlacePoint = { name: string; lat: number; lon: number; stop_id?: string | null };

export type Leg = {
  kind: "walk" | "ride";
  from: PlacePoint;
  to: PlacePoint;
  depart: string;
  arrive: string;
  duration_s: number;
  path: [number, number][];
  distance_m: number | null;
  line: LineSummary | null;
  direction: number | null;
  headsign: string | null;
  stops: number | null;
  wait_s: number | null;
  wait_source: "en direct" | "horaire" | "estimé" | null;
  dashed: boolean | null;
};

export type Itinerary = {
  depart: string;
  arrive: string;
  duration_s: number;
  walk_m: number;
  transfers: number;
  live: boolean;
  legs: Leg[];
};

/** A place for the planner: a stop, or a point (my position, a point tapped on the map). */
export type PlanPlace = { stop_id: string; name: string } | { lat: number; lon: number; name: string };

export const searchStops = (q: string) => request<StopHit[]>(`/stops/search?q=${encodeURIComponent(q)}`);

export const planRoute = (origin: PlanPlace, destination: PlanPlace) =>
  request<Itinerary[]>("/routes/plan", { method: "POST", body: JSON.stringify({ origin, destination }) });

export type PlaceHit = {
  name: string;
  detail: string;
  lat: number;
  lon: number;
  kind: string | null;
  stop_distance_m: number | null; // distance to the nearest stop of the network
};

/** Addresses and places (OpenStreetMap). Call on submit only: Nominatim forbids autocomplete. */
export const searchPlaces = (q: string) => request<PlaceHit[]>(`/places/search?q=${encodeURIComponent(q)}`);
