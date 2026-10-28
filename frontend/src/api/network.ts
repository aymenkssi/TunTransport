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

export type Fix = { t: number; lat: number; lon: number; accuracy: number };

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
export const getLive = () => request<Record<string, number>>("/live");

export const getVehicles = (lineId: string, stopId?: string) =>
  request<Vehicle[]>(`/lines/${encodeURIComponent(lineId)}/vehicles${stopId ? `?stop_id=${encodeURIComponent(stopId)}` : ""}`);

export const startTrip = (lineId: string, direction: number) =>
  authed<TripStarted>("/trips", { method: "POST", body: JSON.stringify({ line_id: lineId, direction }) });

export const postPositions = (tripId: string, fixes: Fix[]) =>
  authed<PositionResult>(`/trips/${tripId}/positions`, { method: "POST", body: JSON.stringify({ fixes }) });

export const endTrip = (tripId: string) => authed<{ ok: boolean }>(`/trips/${tripId}/end`, { method: "POST" });
