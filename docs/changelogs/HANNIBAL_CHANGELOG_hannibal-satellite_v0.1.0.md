# Changelog (mirror of hannibal-satellite/CHANGELOG.md)

All Hannibal work is logged here, with an explanation of what changed and why, and what was and was not verified. Newest first. Mirrored to Google Drive, OneDrive and GitHub.

## [0.1.0] - 2026-10-11

### Added
- hannibal_sat/tle.py - TLE ingest from CelesTrak (no login) and optional Space-Track (credentials from SPACETRACK_USER / SPACETRACK_PASS), with a 2-hour on-disk cache.
- hannibal_sat/propagate.py - SGP4 propagation (sgp4 library) and TEME to WGS84 lat/lon/alt. Decayed or invalid objects return None instead of raising.
- hannibal_sat/kml.py - Google Earth export: time-animated gx:Track KML, a live-position snapshot KML, and a NetworkLink wrapper for Google Earth Pro.
- hannibal_sat/czml.py - CZML export for CesiumJS.
- viewer/index.html - CesiumJS globe that loads the CZML. Optional Google Photorealistic 3D Tiles via ?gkey=... in the URL (key never stored in code).
- hannibal_sat/fred.py - FRED API client with caching and rate limiting; key from FRED_API_KEY, scrubbed from error messages.
- hannibal_sat/hannibal_bridge.py - adapter for hannibal_orbital.py: takes TLEs from the existing get_satellite() provider (hannibal_net masking, caching and rate limits stay in force) and adds an [E] export screen via register(MENU).
- python -m hannibal_sat CLI (kml, czml, watch, fred), tests, .gitignore, .env.example, README.

### Verified
- 7 of 7 unit tests pass.
- Live CelesTrak fetch worked: 19 "stations" TLEs downloaded, 19 tracks written.

### Not verified
- Cesium viewer not opened in a browser; KML not opened in Google Earth (files are structurally valid only).
- hannibal_bridge.py written against hannibal_orbital.py's code but not run inside Hannibal.
- Positions checked for plausibility, not against an independent reference; TEME-to-ECEF ignores polar motion (display-grade).
- data/sample_stations.tle is synthetic test data.
- Nothing pushed to GitHub (the GitHub login in this session was rejected as invalid).
- Not yet mirrored to OneDrive (Microsoft 365 connector not connected).

### Why
Show satellites from the orbital module on Google Earth and on a Cesium globe next to other globe sources (BlueGlobe), without breaking the module's secret-masking design.
