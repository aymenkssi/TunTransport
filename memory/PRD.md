# TunTransport — PRD

## Original Problem Statement
Collaborative Android app where passengers share the live position of the public transport they ride
(bus, metro, train), so others know where it is: "Waze for public transport", for Tunisia.

## User Choices
- Lines, stops, timetables and shapes from tunismapper.com.
- Same stack and organization as Neon Strike: Expo app, FastAPI + MongoDB backend, admin page, Docker deploy.
- French interface.

## Architecture
- **Frontend**: Expo SDK 54 + expo-router (portrait). Map = MapLibre GL JS in react-native-webview
  (iframe on web) with OpenFreeMap tiles, no API key. Sharing = expo-location `startLocationUpdatesAsync`
  with an Android foreground service (no background-location permission), task in expo-task-manager,
  state persisted in AsyncStorage. Anonymous user token in expo-secure-store.
- **Backend**: FastAPI + MongoDB (motor). Network loaded in memory from `data/network.json`. The server
  validates each trace against the declared line/direction and only stores the position along the shape
  (`contributions`, TTL 5 min). Vehicles = clustering of passengers along the shape; reliability from
  freshness × confirmations × agreement; ETA = remaining distance / bounded speed.
- **Admin**: `/admin` (token) — live vehicles, stats, network reload.
- **Deploy**: docker compose (api + mongo + Caddy) or Traefik variant, site with privacy policy, backups,
  monthly network re-import.

## Implemented (2026-10)
- [x] Importer for 228 lines (stop reordering, outlier stops, Douglas-Peucker shapes).
- [x] API: users, lines, suggest, trips, positions, vehicles + ETA, live counts, data deletion, admin.
  30 backend tests.
- [x] App: lines list (search, modes, live badges), line screen (map, direction, live vehicles, ETA,
  timetable), trip sharing with auto-stop, about/privacy/delete data.

## Known Constraints
- Real shapes for only 18 lines; others are stop-to-stop straight lines (wider tolerance, dashed).
- No licence stated by tunismapper.com: get permission before serving the data publicly.
- Positions are polled (10 s), not pushed.

## Backlog / Next
- P0: domain + deploy; replace `https://api.example.com` in eas.json; first field tests on metro lines.
- P1: better shapes (OpenStreetMap relations, or learned from shared trips).
- P1: "my bus is coming" notifications; stable vehicle ids; automatic line suggestion in the share flow.
- P2: WebSocket push; learned ETA per segment and hour; contributor reputation; reports (crowded,
  breakdown, detour); Arabic interface; louages.
