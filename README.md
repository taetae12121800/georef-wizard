# georef-wizard

ArcGIS Pro scripts.

## georef_wizard.py

Step-by-step georeferencing tool (PDF control point picking, TIFF
extraction, georeferencing).

## populate_location_with_direction.py

Location population script for ArcGIS Pro. Run it from the Python window
with the project open, pick the target layer, and click Run.

It sets `LOCATION` on the selected layer to:

    <street>, <direction> <address>      e.g.  Bond RD, N/O 9201 OPAL CREST CT

How it works:

1. Generate Near Table against `EG_MAD` (300 ft) -> `NEAR_FID` gives the
   address (`FULLADDRES`), `NEAR_ANGLE` gives the direction (N/O, S/O,
   E/O, W/O).
2. Generate Near Table against `EG_STREETS` (300 ft) -> `FULLSTREET`
   gives the street the feature actually sits on.
3. Edits are written inside an edit session; both memory tables are
   deleted afterward.

If the street layer is missing from the map or the street lookup fails,
`LOCATION` falls back to `<direction> <address>` with no other change in
behavior.

Search radii and layer names are set inline near the top of `run()`.
