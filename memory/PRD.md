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
- [x] Journey planner (time-dependent Dijkstra, walking + transfers, live waits from shared vehicles,
  official timetables for trains/RFR, estimated waits for metro/bus whose source timetable is hourly).
- [x] Anti-fraud (backend/trust.py): stationary (<100 m in 4 min, off terminus), walking (3–7 km/h avg, no
  peak >10 km/h over 3 min), mocked GPS (trip ended), hidden reputation (confirmed vs solo/rejected/
  reported/mocked; untrusted-only vehicles hidden), "vehicle does not exist" reports (2, or 3 if confirmed).
- [x] Planner: departure time choice (now, +30 min…, tomorrow) and, when nothing runs (night), the first
  possible trip from the timetables of the lines near the origin, departing just in time.
- [x] Local address index for Grand Tunis (tools/import_places.py from Overpass, backend/geocoder.py):
  typo tolerance (1 edit/word), prefix autocomplete, house numbers, aliases (Avicenne = Ibn Sina, roman
  numerals), Arabic names, optional quartier/city words; Nominatim only as a submit-time fallback.
  Photon was evaluated and rejected: no typo tolerance on the test address.
- [x] App: live map home, journey planner tab, lines list (search, modes, live badges), line screen (map, direction, live vehicles, ETA,
  timetable), trip sharing with auto-stop, about/privacy/delete data.

## Known Constraints
- Real shapes for only 18 lines; others are stop-to-stop straight lines (wider tolerance, dashed).
- No licence stated by tunismapper.com: get permission before serving the data publicly.
- Positions are polled (10 s), not pushed.

## Backlog / Next
- P0: register tuntransport.academy DNS + deploy (eas.json already points to api.tuntransport.academy); first field tests on metro lines.
- P1: better shapes (OpenStreetMap relations, or learned from shared trips).
- P1: "my bus is coming" notifications; stable vehicle ids; automatic line suggestion in the share flow.
- P2: WebSocket push; learned ETA per segment and hour; contributor reputation; reports (crowded,
  breakdown, detour); Arabic interface; louages.
