# =============================================================================
# CELL 1: Download Roads & Hospitals from OpenStreetMap
# Paste each section into a separate ArcGIS Pro Notebook cell
# =============================================================================

# ---- CELL 1: Setup ----
import arcpy
import os
import json
import urllib.request
import urllib.parse
import time

arcpy.env.overwriteOutput = True

WORKSPACE = r"D:\Internship\hand\Hand_folde"

# Get bounding box from your DEM raster extent
DEM_PATH = r"D:\Internship\hand\Bease_River_Basin_DEM-002.tif"
desc = arcpy.Describe(DEM_PATH)
extent = desc.extent

# Project extent to WGS84 (lat/lon) if DEM is in UTM/projected coordinates
dem_sr = desc.spatialReference
wgs84 = arcpy.SpatialReference(4326)

if dem_sr.type == "Projected":
    # Reproject extent corners to WGS84
    ll = arcpy.PointGeometry(arcpy.Point(extent.XMin, extent.YMin), dem_sr).projectAs(wgs84)
    ur = arcpy.PointGeometry(arcpy.Point(extent.XMax, extent.YMax), dem_sr).projectAs(wgs84)
    SOUTH = ll.firstPoint.Y
    WEST = ll.firstPoint.X
    NORTH = ur.firstPoint.Y
    EAST = ur.firstPoint.X
else:
    SOUTH = extent.YMin
    WEST = extent.XMin
    NORTH = extent.YMax
    EAST = extent.XMax

arcpy.AddMessage(f"DEM Spatial Reference: {dem_sr.name}")
arcpy.AddMessage(f"Extent extracted from: {DEM_PATH}")

# Output paths
ROADS_WGS84 = os.path.join(WORKSPACE, "roads_wgs84.shp")
HOSPITALS_WGS84 = os.path.join(WORKSPACE, "hospitals_wgs84.shp")
ROADS_UTM = os.path.join(WORKSPACE, "roads.shp")
HOSPITALS_UTM = os.path.join(WORKSPACE, "hospitals.shp")

# Default speeds (km/h) by road type for travel time calculation
default_speeds = {
    "motorway": 80, "trunk": 60, "primary": 50, "secondary": 40,
    "tertiary": 30, "residential": 20, "unclassified": 20,
    "service": 15, "track": 10
}

arcpy.AddMessage("Setup complete.")
arcpy.AddMessage(f"Bounding box: ({SOUTH}, {WEST}, {NORTH}, {EAST})")

# ---- CELL 2: Download Road Network from OSM (with chunking & retry) ----
arcpy.AddMessage("=" * 50)
arcpy.AddMessage("DOWNLOADING ROAD NETWORK FROM OPENSTREETMAP")
arcpy.AddMessage("=" * 50)

url = "https://overpass-api.de/api/interpreter"

# Split bounding box into 4 quadrants to avoid API timeout on large areas
mid_lat = (SOUTH + NORTH) / 2
mid_lon = (WEST + EAST) / 2

chunks = [
    (SOUTH, WEST, mid_lat, mid_lon),    # SW
    (SOUTH, mid_lon, mid_lat, EAST),     # SE
    (mid_lat, WEST, NORTH, mid_lon),     # NW
    (mid_lat, mid_lon, NORTH, EAST),     # NE
]

nodes = {}
ways = []

for i, (s, w, n, e) in enumerate(chunks, 1):
    overpass_query = f"""
    [out:json][timeout:300];
    (
      way["highway"~"motorway|trunk|primary|secondary|tertiary|residential|unclassified|service|track"]
        ({s},{w},{n},{e});
    );
    out body;
    >;
    out skel qt;
    """

    for attempt in range(1, 4):
        try:
            arcpy.AddMessage(f"  Chunk {i}/4 (attempt {attempt}/3)...")
            data = urllib.parse.urlencode({"data": overpass_query}).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=600) as response:
                chunk_result = json.loads(response.read().decode("utf-8"))

            for element in chunk_result.get("elements", []):
                if element["type"] == "node":
                    nodes[element["id"]] = (element["lon"], element["lat"])
                elif element["type"] == "way":
                    ways.append(element)
            break
        except Exception as ex:
            arcpy.AddMessage(f"    Attempt {attempt} failed: {ex}")
            if attempt < 3:
                arcpy.AddMessage(f"    Waiting 30 seconds before retry...")
                time.sleep(30)

    time.sleep(5)  # Pause between chunks

# Remove duplicate ways (edges shared between quadrants)
seen_ids = set()
unique_ways = []
for w in ways:
    if w["id"] not in seen_ids:
        seen_ids.add(w["id"])
        unique_ways.append(w)
ways = unique_ways

arcpy.AddMessage(f"Downloaded {len(ways)} road segments and {len(nodes)} nodes.")

# ---- CELL 3: Create Road Shapefile ----
arcpy.AddMessage("Creating road shapefile...")
sr = arcpy.SpatialReference(4326)

if arcpy.Exists(ROADS_WGS84):
    arcpy.management.Delete(ROADS_WGS84)

arcpy.management.CreateFeatureclass(
    os.path.dirname(ROADS_WGS84),
    os.path.basename(ROADS_WGS84),
    "POLYLINE",
    spatial_reference=sr
)

arcpy.management.AddField(ROADS_WGS84, "osm_id", "DOUBLE")
arcpy.management.AddField(ROADS_WGS84, "highway", "TEXT", field_length=50)
arcpy.management.AddField(ROADS_WGS84, "name", "TEXT", field_length=200)
arcpy.management.AddField(ROADS_WGS84, "maxspeed", "SHORT")
arcpy.management.AddField(ROADS_WGS84, "oneway", "TEXT", field_length=10)
arcpy.management.AddField(ROADS_WGS84, "surface", "TEXT", field_length=50)

fields = ["SHAPE@", "osm_id", "highway", "name", "maxspeed", "oneway", "surface"]
road_count = 0

with arcpy.da.InsertCursor(ROADS_WGS84, fields) as cursor:
    for way in ways:
        tags = way.get("tags", {})
        highway_type = tags.get("highway", "unclassified")

        coords = []
        for node_id in way.get("nodes", []):
            if node_id in nodes:
                coords.append(arcpy.Point(*nodes[node_id]))

        if len(coords) < 2:
            continue

        polyline = arcpy.Polyline(arcpy.Array(coords), sr)

        speed_str = tags.get("maxspeed", "")
        try:
            speed = int(speed_str)
        except (ValueError, TypeError):
            speed = default_speeds.get(highway_type, 20)

        cursor.insertRow([
            polyline,
            way["id"],
            highway_type,
            tags.get("name", ""),
            speed,
            tags.get("oneway", "no"),
            tags.get("surface", "")
        ])
        road_count += 1

arcpy.AddMessage(f"Saved {road_count} road features.")

# Add travel time field
arcpy.management.AddField(ROADS_WGS84, "length_km", "DOUBLE")
arcpy.management.AddField(ROADS_WGS84, "travel_min", "DOUBLE")

with arcpy.da.UpdateCursor(ROADS_WGS84, ["SHAPE@LENGTH", "maxspeed", "length_km", "travel_min"]) as cursor:
    for row in cursor:
        length_km = row[0] * 111.0
        speed = row[1] if row[1] and row[1] > 0 else 20
        travel_min = (length_km / speed) * 60.0
        row[2] = round(length_km, 4)
        row[3] = round(travel_min, 4)
        cursor.updateRow(row)

arcpy.AddMessage("Travel time field calculated.")

# ---- CELL 4: Download Hospital Locations from OSM ----
arcpy.AddMessage("=" * 50)
arcpy.AddMessage("DOWNLOADING HOSPITAL LOCATIONS FROM OPENSTREETMAP")
arcpy.AddMessage("=" * 50)

time.sleep(10)  # Wait longer to respect Overpass API rate limits

hosp_query = f"""
[out:json][timeout:300];
(
  node["amenity"="hospital"]({SOUTH},{WEST},{NORTH},{EAST});
  way["amenity"="hospital"]({SOUTH},{WEST},{NORTH},{EAST});
  node["amenity"="clinic"]({SOUTH},{WEST},{NORTH},{EAST});
  node["amenity"="doctors"]({SOUTH},{WEST},{NORTH},{EAST});
  node["healthcare"="hospital"]({SOUTH},{WEST},{NORTH},{EAST});
  node["healthcare"="clinic"]({SOUTH},{WEST},{NORTH},{EAST});
  node["building"="hospital"]({SOUTH},{WEST},{NORTH},{EAST});
);
out center;
"""

# Retry up to 3 times if Overpass API times out
hosp_result = None
for attempt in range(1, 4):
    try:
        arcpy.AddMessage(f"Querying Overpass API (attempt {attempt}/3)...")
        data = urllib.parse.urlencode({"data": hosp_query}).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=600) as response:
            hosp_result = json.loads(response.read().decode("utf-8"))
        break
    except Exception as e:
        arcpy.AddMessage(f"  Attempt {attempt} failed: {e}")
        if attempt < 3:
            arcpy.AddMessage(f"  Waiting 30 seconds before retry...")
            time.sleep(30)

hosp_elements = hosp_result.get("elements", []) if hosp_result else []
arcpy.AddMessage(f"Found {len(hosp_elements)} healthcare facilities from OSM.")
if len(hosp_elements) == 0:
    arcpy.AddMessage("  No OSM data retrieved. Will use known hospitals as fallback.")

# ---- CELL 5: Create Hospital Shapefile ----
arcpy.AddMessage("Creating hospital shapefile...")

if arcpy.Exists(HOSPITALS_WGS84):
    arcpy.management.Delete(HOSPITALS_WGS84)

arcpy.management.CreateFeatureclass(
    os.path.dirname(HOSPITALS_WGS84),
    os.path.basename(HOSPITALS_WGS84),
    "POINT",
    spatial_reference=sr
)

arcpy.management.AddField(HOSPITALS_WGS84, "osm_id", "DOUBLE")
arcpy.management.AddField(HOSPITALS_WGS84, "name", "TEXT", field_length=200)
arcpy.management.AddField(HOSPITALS_WGS84, "fac_type", "TEXT", field_length=50)
arcpy.management.AddField(HOSPITALS_WGS84, "emergency", "TEXT", field_length=10)
arcpy.management.AddField(HOSPITALS_WGS84, "phone", "TEXT", field_length=50)
arcpy.management.AddField(HOSPITALS_WGS84, "beds", "SHORT")

# Known major hospitals in Kullu District (fallback + supplement)
known_hospitals = [
    {"name": "Regional Hospital Kullu", "lon": 77.1095, "lat": 31.9579,
     "type": "hospital", "emergency": "yes"},
    {"name": "Mission Hospital Manali", "lon": 77.1887, "lat": 32.2396,
     "type": "hospital", "emergency": "yes"},
    {"name": "Lady Willingdon Hospital Manali", "lon": 77.1773, "lat": 32.2432,
     "type": "hospital", "emergency": "yes"},
    {"name": "Civil Hospital Bhuntar", "lon": 77.1584, "lat": 31.8776,
     "type": "hospital", "emergency": "yes"},
    {"name": "PHC Banjar", "lon": 77.3397, "lat": 31.6388,
     "type": "clinic", "emergency": "yes"},
    {"name": "CHC Nagar", "lon": 77.1300, "lat": 32.0400,
     "type": "hospital", "emergency": "yes"},
]

hosp_fields = ["SHAPE@", "osm_id", "name", "fac_type", "emergency", "phone", "beds"]
added_names = set()
hosp_count = 0

with arcpy.da.InsertCursor(HOSPITALS_WGS84, hosp_fields) as cursor:
    # Add OSM data
    for elem in hosp_elements:
        tags = elem.get("tags", {})

        if elem["type"] == "node":
            lon, lat = elem["lon"], elem["lat"]
        elif "center" in elem:
            lon, lat = elem["center"]["lon"], elem["center"]["lat"]
        else:
            continue

        name = tags.get("name", tags.get("name:en", "Unknown Facility"))
        fac_type = tags.get("amenity", tags.get("healthcare", "hospital"))
        emergency = tags.get("emergency", "unknown")
        phone = tags.get("phone", tags.get("contact:phone", ""))

        try:
            beds = int(tags.get("beds", 0))
        except (ValueError, TypeError):
            beds = 0

        point = arcpy.PointGeometry(arcpy.Point(lon, lat), sr)
        cursor.insertRow([point, elem["id"], name, fac_type, emergency, phone, beds])
        added_names.add(name.lower())
        hosp_count += 1

    # Add known hospitals not already in OSM
    for hosp in known_hospitals:
        if hosp["name"].lower() not in added_names:
            point = arcpy.PointGeometry(arcpy.Point(hosp["lon"], hosp["lat"]), sr)
            cursor.insertRow([point, 0, hosp["name"], hosp["type"],
                              hosp["emergency"], "", 0])
            hosp_count += 1
            arcpy.AddMessage(f"  + Added known hospital: {hosp['name']}")

arcpy.AddMessage(f"Saved {hosp_count} healthcare facilities.")

# ---- CELL 6: Project to UTM Zone 43N ----
arcpy.AddMessage("=" * 50)
arcpy.AddMessage("PROJECTING DATA TO UTM ZONE 43N")
arcpy.AddMessage("=" * 50)

utm_sr = arcpy.SpatialReference(32643)

arcpy.management.Project(ROADS_WGS84, ROADS_UTM, utm_sr)
arcpy.AddMessage(f"Roads projected to UTM 43N: {ROADS_UTM}")

arcpy.management.Project(HOSPITALS_WGS84, HOSPITALS_UTM, utm_sr)
arcpy.AddMessage(f"Hospitals projected to UTM 43N: {HOSPITALS_UTM}")

# ---- CELL 7: Add to Map Display ----
aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

if active_map:
    active_map.addDataFromPath(ROADS_UTM)
    active_map.addDataFromPath(HOSPITALS_UTM)
    arcpy.AddMessage("Roads and Hospitals added to current map.")
else:
    arcpy.AddMessage("No active map. Open a map to auto-add layers.")

arcpy.AddMessage("=" * 50)
arcpy.AddMessage("ALL DATA READY!")
arcpy.AddMessage(f"  Roads:     {ROADS_UTM}")
arcpy.AddMessage(f"  Hospitals: {HOSPITALS_UTM}")
arcpy.AddMessage("You can now run the Emergency Routing notebook.")
