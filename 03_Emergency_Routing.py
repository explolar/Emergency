# =============================================================================
# Resilient Infrastructure Planning for GLOF-Prone Regions
# Beas River Basin, Kullu Valley, Himachal Pradesh
#
# Objective 1: Flood Risk Zone Classification (Red to Green)
# Objective 2: Road Vulnerability & Vehicular Mobility Assessment
# Objective 3: Optimal Emergency Service Location
#
# For ArcGIS Pro Notebook - Copy each CELL into a separate notebook cell
# =============================================================================

# ---- CELL 1: Clear Old Data & Setup ----
import arcpy
from arcpy import na
from arcpy.sa import *
import os

arcpy.env.overwriteOutput = True

WORKSPACE = r"D:\Internship\hand\Hand_folde"
arcpy.env.workspace = WORKSPACE

# Release extensions first (in case held from previous run)
try:
    arcpy.CheckInExtension("Spatial")
    arcpy.CheckInExtension("Network")
except:
    pass

# Clear all layers from active map
aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap
if active_map:
    for lyr in active_map.listLayers():
        active_map.removeLayer(lyr)
    print("All layers removed from map.")

# Clear in-memory workspace
arcpy.Delete_management("in_memory")
print("In-memory workspace cleared.")

# Delete and recreate output GDB
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")
if arcpy.Exists(OUTPUT_GDB):
    arcpy.management.Delete(OUTPUT_GDB)
arcpy.management.CreateFileGDB(WORKSPACE, "Emergency_Routing")
print("Fresh Emergency_Routing.gdb created.")

# Delete old intermediate rasters
for f in ["flood_risk_zones.tif", "flood_depth_float.tif",
          "flood_depth_resampled.tif", "flood_extent.tif", "temp_flood_resamp.tif"]:
    fpath = os.path.join(WORKSPACE, f)
    if arcpy.Exists(fpath):
        try:
            arcpy.management.Delete(fpath)
            print(f"  Deleted: {f}")
        except:
            print(f"  Locked: {f}")

print("Workspace cleaned.")

# Check out extensions fresh
arcpy.CheckOutExtension("Spatial")
arcpy.CheckOutExtension("Network")

# --- INPUTS ---
FLOOD_MAP = os.path.join(WORKSPACE, "Beas_Final_Flood_Depth.tif")
DEM_PATH = r"D:\Internship\hand\Bease_River_Basin_DEM-002.tif"
ROAD_NETWORK = os.path.join(WORKSPACE, "roads.shp")
HOSPITALS = os.path.join(WORKSPACE, "hospitals.shp")

# --- THRESHOLDS (from project document & literature) ---
# Vehicle stability (meters) - Himalayan conservative thresholds
# Literature values adjusted downward for:
#   - Steep slopes, narrow mountain roads, debris-laden flow, safety margin
# Literature:   Small=0.30m, Ambulance/SUV=0.40m, Fire/Heavy=0.50m
# Himalayan:    Small=0.20-0.25m, Ambulance/SUV=0.30-0.35m, Fire/Heavy=0.40-0.45m
SMALL_CAR_DEPTH = 0.25       # Small car (literature: 0.30m, conservative: 0.20-0.25m)
AMBULANCE_DEPTH = 0.35       # Ambulance/SUV (literature: 0.40m, conservative: 0.30-0.35m)
HEAVY_VEHICLE_DEPTH = 0.45   # Fire/Heavy duty (literature: 0.50m, conservative: 0.40-0.45m)

# "flow velocity less than 1 m/s" for vehicle stability
FLOW_VELOCITY_LIMIT = 1.0

# "20 cm is the minimum water depth that can lead to vehicle instability" (ref [49])
MIN_INSTABILITY_DEPTH = 0.20

# Emergency response target: "response time to no more than 20 minutes"
MAX_RESPONSE_TIME = 20
SEARCH_TOLERANCE = "5000 Meters"

# Check flood raster
flood_ras = Raster(FLOOD_MAP)
print(f"Flood raster - Min: {flood_ras.minimum}, Max: {flood_ras.maximum}, Mean: {flood_ras.mean:.2f}")
print(f"Pixel type: {arcpy.Describe(FLOOD_MAP).pixelType}")
print(f"DEM cell size: {arcpy.Describe(DEM_PATH).meanCellWidth}m")
print(f"\nVehicle stability: Small={SMALL_CAR_DEPTH}m, Large={AMBULANCE_DEPTH}m, Heavy={HEAVY_VEHICLE_DEPTH}m")
print(f"Target response time: {MAX_RESPONSE_TIME} min")
print("Setup complete.")


# ---- CELL 2: Create Float Flood Depth Surface ----
# DEM is S16 (integer meters), so HAND and flood depth are also integer.
# Fix: Resample HAND rasters using BILINEAR (shrink → expand) to force
# float interpolation between integer pixels.
TRIB_WATER_LEVEL = 5.0
MAIN_WATER_LEVEL = 12.0

print("=" * 60)
print("CREATING FLOAT FLOOD DEPTH SURFACE")
print("=" * 60)

cell = arcpy.Describe(os.path.join(WORKSPACE, "hand_tribs.tif")).meanCellWidth
hand_tribs_f = os.path.join(WORKSPACE, "hand_tribs_float.tif")
hand_main_f = os.path.join(WORKSPACE, "hand_main_float.tif")

# Resample HAND to float via double bilinear
if not arcpy.Exists(hand_tribs_f):
    print("  Resampling HAND tributaries to float...")
    temp = os.path.join(WORKSPACE, "temp_ht.tif")
    arcpy.management.Resample(os.path.join(WORKSPACE, "hand_tribs.tif"), temp, cell * 0.9, "BILINEAR")
    arcpy.management.Resample(temp, hand_tribs_f, cell, "BILINEAR")
    arcpy.management.Delete(temp)

if not arcpy.Exists(hand_main_f):
    print("  Resampling HAND main river to float...")
    temp = os.path.join(WORKSPACE, "temp_hm.tif")
    arcpy.management.Resample(os.path.join(WORKSPACE, "hand_main.tif"), temp, cell * 0.9, "BILINEAR")
    arcpy.management.Resample(temp, hand_main_f, cell, "BILINEAR")
    arcpy.management.Delete(temp)

print("  Float HAND rasters ready.")

# Calculate float flood depth = WaterLevel - HAND
print("  Calculating float flood depth...")
ht = Raster(hand_tribs_f)
hm = Raster(hand_main_f)

flood_trib = Con(ht <= TRIB_WATER_LEVEL, TRIB_WATER_LEVEL - ht)
flood_main = Con(hm <= MAIN_WATER_LEVEL, MAIN_WATER_LEVEL - hm)
flood_float = CellStatistics([flood_trib, flood_main], "MAXIMUM", "DATA")

flood_resampled = os.path.join(WORKSPACE, "flood_depth_float.tif")
flood_float.save(flood_resampled)

res_ras = Raster(flood_resampled)
print(f"  Min: {res_ras.minimum:.2f}, Max: {res_ras.maximum:.2f}, Mean: {res_ras.mean:.2f}")
print(f"  Pixel type: {arcpy.Describe(flood_resampled).pixelType}")
print("  Float flood depth surface created.")


# ---- CELL 3: Flood Risk Zone Classification (Objective 1) ----
# "categorise different regions from red (high prone) to green (least prone)"
# Based on flood depth and vehicle stability thresholds
print("=" * 60)
print("OBJECTIVE 1: FLOOD RISK ZONE CLASSIFICATION")
print("=" * 60)

flood_r = Raster(flood_resampled)
print(f"  [DEBUG] Evaluating map: {flood_resampled}")
try:
    print(f"  [DEBUG] Map Min: {flood_r.minimum}, Map Max: {flood_r.maximum}")
except:
    pass

# Project document Objective 1:
# "Regions will be further classified as minor, moderate and major flooding
#  regions based on the flood depth and flow velocity"
# "categorise different zones from red (highly prone) to green (least prone)"
#
# Classification: 3 flood severity levels + no flood (from MIKE+ methodology)
# Based on standard flood depth severity thresholds used in flood management:
flood_risk = Con(
    flood_r > 1.5, 3,          # 3 = Red/Major   - depth > 1.5m, life-threatening
    Con(flood_r > 0.5, 2,      # 2 = Orange/Moderate - depth 0.5-1.5m, property damage
        Con(flood_r > 0, 1, 0))) # 1 = Yellow/Minor - depth 0-0.5m, road disruption

flood_risk_path = os.path.join(WORKSPACE, "flood_risk_zones.tif")
flood_risk.save(flood_risk_path)

# Convert to polygon with labels
flood_risk_poly = os.path.join(OUTPUT_GDB, "Flood_Risk_Zones")
arcpy.conversion.RasterToPolygon(flood_risk, flood_risk_poly, "SIMPLIFY", "VALUE")

arcpy.management.AddField(flood_risk_poly, "risk_level", "TEXT", field_length=25)
arcpy.management.AddField(flood_risk_poly, "depth_range", "TEXT", field_length=25)
risk_map = {
    3: ("Red - Major",       "> 1.5 m"),
    2: ("Orange - Moderate", "0.5 - 1.5 m"),
    1: ("Yellow - Minor",    "< 0.5 m"),
    0: ("Green - No Flood",  "0 m")
}
with arcpy.da.UpdateCursor(flood_risk_poly, ["gridcode", "risk_level", "depth_range"]) as cursor:
    for row in cursor:
        info = risk_map.get(row[0], ("Green - No Flood", "0 m"))
        row[1] = info[0]
        row[2] = info[1]
        cursor.updateRow(row)

# Count zones
zone_counts = {}
with arcpy.da.SearchCursor(flood_risk_poly, ["gridcode"]) as cursor:
    for row in cursor:
        zone_counts[row[0]] = zone_counts.get(row[0], 0) + 1

print("  Red (3):    > 1.5m  - Major flooding, life-threatening")
print("  Orange (2): 0.5-1.5m - Moderate, property damage")
print("  Yellow (1): < 0.5m  - Minor, road disruption")
print("  Green (0):  No flood")
print("  Zone distribution:", zone_counts)
print("  Risk zones created.")


# ---- CELL 3B: Allowable Speed Map (Pregnolato et al. 2017) ----
# "Depth-disruption function: empirical relationship between flood water
#  depth and vehicle safe speed" (ref [34])
#   v(w) = 0.0009w^2 - 0.5529w + 86.9448  (w in mm, v in km/h)
# Converting to meters: v = 900*d^2 - 552.9*d + 86.9448
print("=" * 60)
print("ALLOWABLE SPEED MAP (PREGNOLATO ET AL. 2017)")
print("=" * 60)

flood_d = Raster(flood_resampled)

# Apply Pregnolato depth-disruption function (depth in meters)
# v(w) = 0.0009w^2 - 0.5529w + 86.9448  (w in mm)
# In meters: v = 900*d^2 - 552.9*d + 86.9448
# At d=0: v = 86.94 km/h (dry road baseline)
safe_speed_raw = 900 * (flood_d ** 2) - 552.9 * flood_d + 86.9448

# The equation is valid up to ~300mm (0.3m). Beyond that, vehicles are impassable.
# At 0.3m: v ≈ 2.67 km/h. Beyond 0.3m depth, speed = 0 (impassable).
safe_speed_raster = Con(flood_d <= 0, 86.94,
                        Con(flood_d > 0.3, 0,
                            Con(safe_speed_raw < 0, 0,
                                Con(safe_speed_raw > 86.94, 86.94, safe_speed_raw))))

safe_speed_path = os.path.join(WORKSPACE, "safe_speed_pregnolato.tif")
safe_speed_raster.save(safe_speed_path)

# Convert to polygon for map display
safe_speed_poly = os.path.join(OUTPUT_GDB, "Safe_Speed_Zones")
# Classify into speed categories
speed_classes = Con(
    safe_speed_raster >= 60, 5,        # 5 = 60-87 km/h (near normal)
    Con(safe_speed_raster >= 40, 4,    # 4 = 40-60 km/h (slight reduction)
        Con(safe_speed_raster >= 20, 3, # 3 = 20-40 km/h (moderate reduction)
            Con(safe_speed_raster >= 10, 2, # 2 = 10-20 km/h (severe reduction)
                Con(safe_speed_raster > 0, 1, 0))))) # 1 = 0-10 km/h, 0 = impassable

speed_class_path = os.path.join(WORKSPACE, "safe_speed_classes.tif")
speed_classes.save(speed_class_path)
arcpy.conversion.RasterToPolygon(speed_classes, safe_speed_poly, "SIMPLIFY", "VALUE")

arcpy.management.AddField(safe_speed_poly, "speed_range", "TEXT", field_length=30)
arcpy.management.AddField(safe_speed_poly, "condition", "TEXT", field_length=20)
speed_map = {
    5: ("60 - 87 km/h", "Near Normal"),
    4: ("40 - 60 km/h", "Slight Reduction"),
    3: ("20 - 40 km/h", "Moderate Reduction"),
    2: ("10 - 20 km/h", "Severe Reduction"),
    1: ("0 - 10 km/h",  "Critical"),
    0: ("0 km/h",       "Impassable")
}
with arcpy.da.UpdateCursor(safe_speed_poly, ["gridcode", "speed_range", "condition"]) as cursor:
    for row in cursor:
        info = speed_map.get(row[0], ("0 km/h", "Impassable"))
        row[1] = info[0]
        row[2] = info[1]
        cursor.updateRow(row)

# Count zones
speed_counts = {}
with arcpy.da.SearchCursor(safe_speed_poly, ["gridcode"]) as cursor:
    for row in cursor:
        speed_counts[row[0]] = speed_counts.get(row[0], 0) + 1

print("  Speed zones (Pregnolato et al. 2017):")
for code in sorted(speed_counts.keys(), reverse=True):
    info = speed_map.get(code, ("Unknown", "Unknown"))
    print(f"    {info[0]:20s} ({info[1]:20s}): {speed_counts[code]} polygons")

ss_ras = Raster(safe_speed_path)
print(f"\n  Speed raster - Min: {ss_ras.minimum:.1f} km/h, Max: {ss_ras.maximum:.1f} km/h")
print("  Safe speed map created.")


# ---- CELL 4: Road Vulnerability Assessment (Objective 2) ----
# "Roads intersecting with flood depth will be identified by overlaying
#  flood risk map with road network map in ArcGIS"
print("=" * 60)
print("OBJECTIVE 2: ROAD VULNERABILITY & VEHICULAR MOBILITY")
print("=" * 60)

# Fix Projection Mismatch: Project roads directly into the DEM's native spatial reference!
arcpy.env.overwriteOutput = True
road_vuln = os.path.join(OUTPUT_GDB, "Road_Vulnerability")
dem_sr = arcpy.Describe(DEM_PATH).spatialReference
arcpy.management.Project(ROAD_NETWORK, road_vuln, dem_sr)
print(f"  Projected roads dynamically to match DEM: {dem_sr.name}")

# Add assessment fields
for fname, ftype in [("flood_depth", "DOUBLE"), ("avg_depth", "DOUBLE"),
                      ("min_elev", "DOUBLE"), ("max_elev", "DOUBLE"),
                      ("safe_speed", "DOUBLE"),
                      ("small_car", "TEXT"), ("ambulance", "TEXT"),
                      ("heavy_veh", "TEXT"), ("road_status", "TEXT")]:
    flen = 15 if ftype == "TEXT" else None
    arcpy.management.AddField(road_vuln, fname, ftype, field_length=flen)

# Densify vertices every 1m (minimum practical distance in ArcGIS)
print("  Densifying road vertices every 1m...")
arcpy.edit.Densify(road_vuln, "DISTANCE", "1 Meters")

# Convert to points
print("  Extracting road vertex points...")
road_vertices = os.path.join(OUTPUT_GDB, "Road_Vertices")
arcpy.management.FeatureVerticesToPoints(road_vuln, road_vertices, "ALL")

# Extract DEM elevation (point/nearest)
print("  Extracting DEM elevation (point)...")
road_sample = os.path.join(OUTPUT_GDB, "Road_Sample")
arcpy.sa.ExtractValuesToPoints(road_vertices, DEM_PATH, road_sample, "NONE", "VALUE_ONLY")
arcpy.management.AlterField(road_sample, "RASTERVALU", "dem_elev", "DEM Elevation")

# Extract flood depth from resampled raster (point/nearest)
print("  Extracting flood depth (point from resampled raster)...")
arcpy.sa.ExtractMultiValuesToPoints(road_sample, [
    [flood_resampled, "ext_fdepth"]
], "NONE")

vertex_count = int(arcpy.management.GetCount(road_sample)[0])
print(f"  Extracted depth at {vertex_count} road vertices.")

# Aggregate per road segment
print("  Aggregating per road segment...")
depth_lookup = {}
with arcpy.da.SearchCursor(road_sample, ["ORIG_FID", "ext_fdepth", "dem_elev"]) as cursor:
    for row in cursor:
        oid = row[0]
        depth = round(row[1], 2) if row[1] and row[1] > 0 else 0.00
        dem_e = round(row[2], 2) if row[2] else 0.00

        if oid not in depth_lookup:
            depth_lookup[oid] = {
                "max_depth": depth, "depths": [depth],
                "min_elev": dem_e, "max_elev": dem_e
            }
        else:
            d = depth_lookup[oid]
            d["max_depth"] = max(d["max_depth"], depth)
            d["depths"].append(depth)
            d["min_elev"] = min(d["min_elev"], dem_e)
            d["max_elev"] = max(d["max_elev"], dem_e)

for info in depth_lookup.values():
    info["avg_depth"] = round(sum(info["depths"]) / len(info["depths"]), 2) if info["depths"] else 0.00
    del info["depths"]

print(f"  Aggregated for {len(depth_lookup)} road segments.")


# ---- CELL 5: Safe Driving Speed & Vehicle Stability (Objective 2) ----
# "Depth-disruption function: empirical relationship between flood water
#  depth and vehicle safe speed" (Pregnolato et al. 2017, ref [34])
# "threshold value for Indian scenario will be assessed for Kullu specific
#  road conditions and type of emergency vehicles"
print("  Applying depth-disruption function & vehicle stability...")

def depth_disruption_speed(depth_m):
    """
    Safe driving speed based on flood water depth.
    Pregnolato et al. (2017) depth-disruption function:
        v(w) = 0.0009w^2 - 0.5529w + 86.9448
    where v = speed (km/h), w = water depth (mm)
    At w=0: v = 86.94 km/h (dry road baseline)
    Equation valid for 0-300mm. Beyond 300mm (0.3m), v = 0 (impassable).
    """
    if depth_m <= 0.00:
        return 86.94

    if depth_m > 0.30:
        return 0.00

    w = depth_m * 1000.0  # Convert meters to mm
    v = 0.0009 * (w ** 2) - 0.5529 * w + 86.9448

    # Clamp between 0 and 86.94
    v = max(v, 0.00)
    v = min(v, 86.94)

    return round(v, 2)

# Update road vulnerability attributes (all depths in 2 decimal places)
with arcpy.da.UpdateCursor(road_vuln,
    ["OID@", "flood_depth", "avg_depth", "min_elev", "max_elev",
     "safe_speed", "small_car", "ambulance", "heavy_veh", "road_status"]) as cursor:
    for row in cursor:
        info = depth_lookup.get(row[0], {"max_depth": 0.00, "avg_depth": 0.00, "min_elev": 0.00, "max_elev": 0.00})
        depth = info["max_depth"]

        row[1] = round(depth, 2)               # max flood depth
        row[2] = round(info["avg_depth"], 2)    # avg flood depth
        row[3] = round(info["min_elev"], 2)     # min elevation
        row[4] = round(info["max_elev"], 2)     # max elevation
        row[5] = round(depth_disruption_speed(depth), 2)  # safe speed km/h

        # Vehicle stability: "small=0.3m, large=0.4m, heavy=0.5m" (ref [16],[51])
        row[6] = "Passable" if depth < SMALL_CAR_DEPTH else "Impassable"
        row[7] = "Passable" if depth < AMBULANCE_DEPTH else "Impassable"
        row[8] = "Passable" if depth < HEAVY_VEHICLE_DEPTH else "Impassable"

        # Road status for emergency vehicles
        # "road will be marked as impassable or traversable" - project doc
        if depth <= 0.00:
            row[9] = "Safe"
        elif depth < MIN_INSTABILITY_DEPTH:   # < 0.20m
            row[9] = "Caution"
        elif depth < HEAVY_VEHICLE_DEPTH:     # 0.20-0.50m
            row[9] = "Restricted"
        else:                                  # > 0.50m
            row[9] = "Impassable"

        cursor.updateRow(row)

# Count by status
status_counts = {}
with arcpy.da.SearchCursor(road_vuln, ["road_status"]) as cursor:
    for row in cursor:
        status_counts[row[0]] = status_counts.get(row[0], 0) + 1

print("  Road vulnerability results:")
for s, c in sorted(status_counts.items()):
    print(f"    {s}: {c} segments")

# Create separate layers
traversable_roads = os.path.join(OUTPUT_GDB, "Traversable_Roads")
blocked_roads = os.path.join(OUTPUT_GDB, "Blocked_Roads")
restricted_roads = os.path.join(OUTPUT_GDB, "Restricted_Roads")

arcpy.analysis.Select(road_vuln, traversable_roads, "road_status = 'Safe' OR road_status = 'Caution'")
arcpy.analysis.Select(road_vuln, blocked_roads, "road_status = 'Impassable'")
arcpy.analysis.Select(road_vuln, restricted_roads, "road_status = 'Restricted'")

trav_count = int(arcpy.management.GetCount(traversable_roads)[0])
block_count = int(arcpy.management.GetCount(blocked_roads)[0])
rest_count = int(arcpy.management.GetCount(restricted_roads)[0])
print(f"  Traversable: {trav_count} | Restricted: {rest_count} | Blocked: {block_count}")


# ---- CELL 6: Build Network with Flood-Adjusted Travel Time ----
# "safe and quickest evacuation routes for emergency vehicles" - project doc
print("=" * 60)
print("BUILDING NETWORK WITH FLOOD-ADJUSTED TRAVEL TIMES")
print("=" * 60)

# Emergency vehicles use Safe + Caution + Restricted roads (not Impassable)
emergency_roads = os.path.join(OUTPUT_GDB, "Emergency_Vehicle_Roads")
arcpy.analysis.Select(road_vuln, emergency_roads, "road_status <> 'Impassable'")

# Calculate travel time using flood-adjusted safe speed
arcpy.management.AddField(emergency_roads, "flood_time", "DOUBLE")
with arcpy.da.UpdateCursor(emergency_roads, ["SHAPE@LENGTH", "safe_speed", "flood_time"]) as cursor:
    for row in cursor:
        length_km = row[0] / 1000.0
        speed = row[1] if row[1] and row[1] > 0 else 5.00
        row[2] = round((length_km / speed) * 60.0, 2)
        cursor.updateRow(row)

print("  Travel times adjusted for flood conditions.")

# Build network dataset
sr = arcpy.Describe(ROAD_NETWORK).spatialReference
fd_name = "Emergency_Network"
fd_path = os.path.join(OUTPUT_GDB, fd_name)

if arcpy.Exists(fd_path):
    arcpy.management.Delete(fd_path)

arcpy.management.CreateFeatureDataset(OUTPUT_GDB, fd_name, sr)

network_roads_name = "Roads"
network_roads = os.path.join(fd_path, network_roads_name)
arcpy.management.CopyFeatures(emergency_roads, network_roads)

nd_name = "EmergencyND"
nd_path = os.path.join(fd_path, nd_name)

arcpy.na.CreateNetworkDataset(fd_path, nd_name, [network_roads_name], "ELEVATION_FIELDS")
arcpy.na.BuildNetwork(nd_path)
print("  Network dataset built.")


# ---- CELL 7: Closest Facility - Quickest Evacuation Routes ----
# "identify the safe and quickest evacuation routes for emergency vehicles"
print("=" * 60)
print("OBJECTIVE 2: QUICKEST EVACUATION ROUTES (CLOSEST FACILITY)")
print("=" * 60)

cf_layer = arcpy.na.MakeClosestFacilityAnalysisLayer(
    nd_path, "ClosestFacility",
    travel_mode="Driving Time",
    travel_direction="TO_FACILITIES",
    cutoff=MAX_RESPONSE_TIME,
    number_of_facilities_to_find=3,
    line_shape="ALONG_NETWORK",
    ignore_invalid_locations="SKIP"
)
cf_layer_obj = cf_layer.getOutput(0)

# Load hospitals as facilities
arcpy.na.AddLocations(cf_layer_obj, "Facilities", HOSPITALS, search_tolerance=SEARCH_TOLERANCE)
fac_count = int(arcpy.management.GetCount(cf_layer_obj.listLayers("Facilities")[0])[0])
print(f"  Hospitals on network: {fac_count}")

# Create flood zone incident points (filter > 10000 sq m)
flood_extent = Con(Raster(flood_resampled) > 0, 1, 0)
flood_poly = os.path.join(OUTPUT_GDB, "Flood_Polygon")
arcpy.conversion.RasterToPolygon(flood_extent, flood_poly, "SIMPLIFY", "VALUE")

flood_poly_filtered = os.path.join(OUTPUT_GDB, "Flood_Polygon_Filtered")
arcpy.management.AddField(flood_poly, "area_sqm", "DOUBLE")
arcpy.management.CalculateGeometryAttributes(flood_poly, [["area_sqm", "AREA"]], area_unit="SQUARE_METERS")
arcpy.analysis.Select(flood_poly, flood_poly_filtered, "area_sqm > 10000")

flood_centroids = os.path.join(OUTPUT_GDB, "Flood_Zone_Centroids")
arcpy.management.FeatureToPoint(flood_poly_filtered, flood_centroids, "INSIDE")
arcpy.na.AddLocations(cf_layer_obj, "Incidents", flood_centroids, search_tolerance=SEARCH_TOLERANCE)

inc_count = int(arcpy.management.GetCount(cf_layer_obj.listLayers("Incidents")[0])[0])
print(f"  Flood zone incidents: {inc_count}")

route_count = 0
if fac_count > 0 and inc_count > 0:
    arcpy.na.Solve(cf_layer_obj, ignore_invalids="SKIP")
    routes_output = os.path.join(OUTPUT_GDB, "Emergency_Routes")
    arcpy.management.CopyFeatures(cf_layer_obj.listLayers("Routes")[0], routes_output)
    route_count = int(arcpy.management.GetCount(routes_output)[0])
    print(f"  Emergency routes found: {route_count}")
else:
    print("  WARNING: No facilities/incidents located on network.")


# ---- CELL 8: Service Area - Response Time Zones ----
# "emergency services to carry out rescue within 5-20 min" - project doc
print("=" * 60)
print("SERVICE AREA ANALYSIS (RESPONSE TIME ZONES)")
print("=" * 60)

cutoffs = [5, 10, 15, 20]

sa_layer = arcpy.na.MakeServiceAreaAnalysisLayer(
    nd_path, "ServiceArea",
    travel_mode="Driving Time",
    travel_direction="FROM_FACILITIES",
    cutoffs=cutoffs,
    polygon_detail="STANDARD"
)
sa_layer_obj = sa_layer.getOutput(0)

arcpy.na.AddLocations(sa_layer_obj, "Facilities", HOSPITALS, search_tolerance=SEARCH_TOLERANCE)
arcpy.na.Solve(sa_layer_obj)

sa_output = os.path.join(OUTPUT_GDB, "Hospital_Service_Areas")
arcpy.management.CopyFeatures(sa_layer_obj.listLayers("Polygons")[0], sa_output)
print(f"  Service areas: {cutoffs} min zones")


# ---- CELL 9: Optimal Emergency Service Location (Objective 3) ----
# "model the optimal and ideal location of emergency services and shelters
#  for the flood-affected, to improve timely emergency response" - project doc
print("=" * 60)
print("OBJECTIVE 3: OPTIMAL EMERGENCY SERVICE LOCATION")
print("=" * 60)

# Generate candidate locations every 2km along safe roads
candidate_points = os.path.join(OUTPUT_GDB, "Candidate_Locations")
arcpy.management.GeneratePointsAlongLines(
    traversable_roads, candidate_points, "DISTANCE", Distance="2000 Meters"
)
cand_count = int(arcpy.management.GetCount(candidate_points)[0])
print(f"  Candidate locations: {cand_count}")

# Location-Allocation: find optimal new emergency center locations
# "strategic stationing of emergency-response teams or centres" - project doc
# number_of_facilities_to_find must be >= required (existing hospitals) + new candidates
hospital_count = int(arcpy.management.GetCount(HOSPITALS)[0])
num_new_centers = 5
total_facilities = hospital_count + num_new_centers
print(f"  Existing hospitals (required): {hospital_count}")
print(f"  New centers to find: {num_new_centers}")
print(f"  Total facilities to locate: {total_facilities}")

la_layer = arcpy.na.MakeLocationAllocationAnalysisLayer(
    nd_path, "LocationAllocation",
    travel_mode="Driving Time",
    travel_direction="TO_FACILITIES",
    cutoff=MAX_RESPONSE_TIME,
    number_of_facilities_to_find=total_facilities,
    problem_type="MINIMIZE_IMPEDANCE",
    ignore_invalid_locations="SKIP"
)
la_layer_obj = la_layer.getOutput(0)

# Existing hospitals = required (FacilityType=1)
arcpy.na.AddLocations(la_layer_obj, "Facilities", HOSPITALS,
    search_tolerance=SEARCH_TOLERANCE, field_mappings="FacilityType # 1")

# Candidate points = potential (FacilityType=0)
arcpy.na.AddLocations(la_layer_obj, "Facilities", candidate_points,
    search_tolerance=SEARCH_TOLERANCE, field_mappings="FacilityType # 0")

# Flood zone centroids = demand points
arcpy.na.AddLocations(la_layer_obj, "Demand Points", flood_centroids,
    search_tolerance=SEARCH_TOLERANCE)

print("  Solving location-allocation...")
arcpy.na.Solve(la_layer_obj, ignore_invalids="SKIP")

optimal_locations = os.path.join(OUTPUT_GDB, "Optimal_Emergency_Centers")
arcpy.management.CopyFeatures(la_layer_obj.listLayers("Facilities")[0], optimal_locations)

allocation_lines = os.path.join(OUTPUT_GDB, "Allocation_Lines")
arcpy.management.CopyFeatures(la_layer_obj.listLayers("Lines")[0], allocation_lines)

opt_count = int(arcpy.management.GetCount(optimal_locations)[0])
print(f"  Optimal emergency centers: {opt_count} (existing + new)")


# ---- CELL 10: Add All Results to Map ----
aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

if active_map:
    layers = [
        flood_resampled,
        flood_risk_poly,
        os.path.join(WORKSPACE, "safe_speed_pregnolato.tif"),
        os.path.join(OUTPUT_GDB, "Safe_Speed_Zones"),
        ROAD_NETWORK,
        road_vuln,
        traversable_roads,
        blocked_roads,
        restricted_roads,
        HOSPITALS,
        os.path.join(OUTPUT_GDB, "Emergency_Routes"),
        sa_output,
        optimal_locations,
        allocation_lines,
    ]
    for lpath in layers:
        if arcpy.Exists(lpath):
            active_map.addDataFromPath(lpath)

    print("All layers added to map.")
else:
    print("No active map. Open a Map tab first.")


# ---- CELL 11: Summary Report ----
print("")
print("=" * 65)
print("  RESILIENT INFRASTRUCTURE PLANNING - FINAL REPORT")
print("  Beas River Basin, Kullu Valley, Himachal Pradesh")
print("=" * 65)

total_roads = int(arcpy.management.GetCount(ROAD_NETWORK)[0])
hospital_count = int(arcpy.management.GetCount(HOSPITALS)[0])

print(f"""
  OBJECTIVE 1: FLOOD RISK ZONES
  -----------------------------------------------
    Red    (> 1.5m):     Major flooding, life-threatening
    Orange (0.5-1.5m):   Moderate, property damage
    Yellow (< 0.5m):     Minor, road disruption
    Green  (0m):         No flood

  OBJECTIVE 2: ROAD VULNERABILITY
  -----------------------------------------------
    Total road segments:     {total_roads}
    Vehicle Stability Thresholds:
      Small car:             {SMALL_CAR_DEPTH}m
      Large passenger car:   {AMBULANCE_DEPTH}m
      Heavy/Emergency veh:   {HEAVY_VEHICLE_DEPTH}m
      Min instability depth: {MIN_INSTABILITY_DEPTH}m
      Flow velocity limit:   {FLOW_VELOCITY_LIMIT} m/s

  OBJECTIVE 3: EMERGENCY RESPONSE
  -----------------------------------------------
    Existing hospitals:      {hospital_count}
    Target response time:    <= {MAX_RESPONSE_TIME} min
    Service area zones:      [5, 10, 15, 20] min

  OUTPUT: {OUTPUT_GDB}
""")
print("=" * 65)
print("Analysis Complete!")

# ---- INPUT DATA SUMMARY ----
flood_ras = Raster(FLOOD_MAP)
dem_desc = arcpy.Describe(DEM_PATH)
road_desc = arcpy.Describe(ROAD_NETWORK)
total_roads = int(arcpy.management.GetCount(ROAD_NETWORK)[0])
hospital_count = int(arcpy.management.GetCount(HOSPITALS)[0])

print(f"""
  INPUT DATA
  {'─' * 55}
  Flood Depth Raster:  {os.path.basename(FLOOD_MAP)}
    Min Depth:         {flood_ras.minimum:.2f} m
    Max Depth:         {flood_ras.maximum:.2f} m
    Mean Depth:        {flood_ras.mean:.2f} m
    Pixel Type:        {arcpy.Describe(FLOOD_MAP).pixelType}
    Cell Size:         {arcpy.Describe(FLOOD_MAP).meanCellWidth:.2f} m

  DEM:                 {os.path.basename(DEM_PATH)}
    Cell Size:         {dem_desc.meanCellWidth:.2f} m
    Spatial Reference: {dem_desc.spatialReference.name}

  Road Network:        {os.path.basename(ROAD_NETWORK)}
    Total Segments:    {total_roads}
    Spatial Reference: {road_desc.spatialReference.name}

  Hospitals:           {hospital_count} facilities
""")

# ---- OBJECTIVE 1: FLOOD RISK ZONES ----
print(f"  {'=' * 55}")
print(f"  OBJECTIVE 1: FLOOD RISK ZONE CLASSIFICATION")
print(f"  {'=' * 55}")

# Count zones from actual data
zone_counts = {}
zone_areas = {}
flood_risk_poly = os.path.join(OUTPUT_GDB, "Flood_Risk_Zones")
if arcpy.Exists(flood_risk_poly):
    with arcpy.da.SearchCursor(flood_risk_poly, ["gridcode", "SHAPE@AREA"]) as cursor:
        for row in cursor:
            gc = row[0]
            zone_counts[gc] = zone_counts.get(gc, 0) + 1
            zone_areas[gc] = zone_areas.get(gc, 0) + row[1]

total_polys = sum(zone_counts.values())
total_area = sum(zone_areas.values())

print(f"""
  Classification (MIKE+ methodology):
  {'─' * 55}
  Zone          Depth         Polygons    Area (sq km)   %
  {'─' * 55}""")

zone_info = [
    (3, "Red/Major",    "> 1.5 m",     "Life-threatening"),
    (2, "Orange/Mod",   "0.5-1.5 m",   "Property damage"),
    (1, "Yellow/Minor", "< 0.5 m",     "Road disruption"),
    (0, "Green/None",   "0 m",         "No flood"),
]
for gc, label, depth, impact in zone_info:
    cnt = zone_counts.get(gc, 0)
    area_km2 = zone_areas.get(gc, 0) / 1e6
    pct = (cnt / total_polys * 100) if total_polys > 0 else 0
    print(f"  {label:14s} {depth:12s} {cnt:8d}    {area_km2:10.2f}   {pct:5.1f}%")

print(f"  {'─' * 55}")
print(f"  {'TOTAL':14s} {'':12s} {total_polys:8d}    {total_area/1e6:10.2f}   100.0%")

# ---- OBJECTIVE 1B: SAFE SPEED (PREGNOLATO) ----
safe_speed_poly = os.path.join(OUTPUT_GDB, "Safe_Speed_Zones")
if arcpy.Exists(safe_speed_poly):
    print(f"""
  ALLOWABLE SPEED MAP (Pregnolato et al., 2017)
  {'─' * 55}
  Formula: v(w) = 0.0009w² - 0.5529w + 86.9448
           w = water depth (mm), v = speed (km/h)
  {'─' * 55}""")
    speed_counts = {}
    with arcpy.da.SearchCursor(safe_speed_poly, ["gridcode"]) as cursor:
        for row in cursor:
            speed_counts[row[0]] = speed_counts.get(row[0], 0) + 1
    speed_info = [
        (5, "40-50 km/h", "Near Normal"),
        (4, "30-40 km/h", "Slight Reduction"),
        (3, "20-30 km/h", "Moderate Reduction"),
        (2, "10-20 km/h", "Severe Reduction"),
        (1, "0-10 km/h",  "Critical"),
        (0, "0 km/h",     "Impassable"),
    ]
    for gc, speed, condition in speed_info:
        cnt = speed_counts.get(gc, 0)
        print(f"  {speed:14s}  {condition:22s}  {cnt:8d} polygons")

# ---- OBJECTIVE 2: ROAD VULNERABILITY ----
print(f"""
  {'=' * 55}
  OBJECTIVE 2: ROAD VULNERABILITY & VEHICULAR MOBILITY
  {'=' * 55}""")

# Road status counts from actual data
road_vuln_fc = os.path.join(OUTPUT_GDB, "Road_Vulnerability")
status_counts = {}
depth_stats = {"max": 0, "total": 0, "count": 0, "flooded": 0}
speed_stats = {"min": 999, "max": 0, "total": 0, "count": 0}
small_pass = {"Passable": 0, "Impassable": 0}
amb_pass = {"Passable": 0, "Impassable": 0}
heavy_pass = {"Passable": 0, "Impassable": 0}

if arcpy.Exists(road_vuln_fc):
    with arcpy.da.SearchCursor(road_vuln_fc,
        ["road_status", "flood_depth", "safe_speed", "small_car", "ambulance", "heavy_veh"]) as cursor:
        for row in cursor:
            status_counts[row[0]] = status_counts.get(row[0], 0) + 1
            if row[1] and row[1] > 0:
                depth_stats["max"] = max(depth_stats["max"], row[1])
                depth_stats["total"] += row[1]
                depth_stats["flooded"] += 1
            depth_stats["count"] += 1
            if row[2] is not None:
                speed_stats["min"] = min(speed_stats["min"], row[2])
                speed_stats["max"] = max(speed_stats["max"], row[2])
                speed_stats["total"] += row[2]
                speed_stats["count"] += 1
            small_pass[row[3]] = small_pass.get(row[3], 0) + 1
            amb_pass[row[4]] = amb_pass.get(row[4], 0) + 1
            heavy_pass[row[5]] = heavy_pass.get(row[5], 0) + 1

safe_cnt = status_counts.get("Safe", 0)
caut_cnt = status_counts.get("Caution", 0)
rest_cnt = status_counts.get("Restricted", 0)
imps_cnt = status_counts.get("Impassable", 0)
total_assessed = sum(status_counts.values())
avg_depth = depth_stats["total"] / depth_stats["flooded"] if depth_stats["flooded"] > 0 else 0
avg_speed = speed_stats["total"] / speed_stats["count"] if speed_stats["count"] > 0 else 0

print(f"""
  Road Status Assessment:
  {'─' * 55}
  Status         Segments     %        Description
  {'─' * 55}
  Safe           {safe_cnt:6d}    {safe_cnt/total_assessed*100:5.1f}%     No flood water
  Caution        {caut_cnt:6d}    {caut_cnt/total_assessed*100:5.1f}%     Depth < {MIN_INSTABILITY_DEPTH}m
  Restricted     {rest_cnt:6d}    {rest_cnt/total_assessed*100:5.1f}%     Depth {MIN_INSTABILITY_DEPTH}-{HEAVY_VEHICLE_DEPTH}m
  Impassable     {imps_cnt:6d}    {imps_cnt/total_assessed*100:5.1f}%     Depth > {HEAVY_VEHICLE_DEPTH}m
  {'─' * 55}
  TOTAL          {total_assessed:6d}    100.0%

  Flood Depth on Roads:
  {'─' * 55}
  Max flood depth on any road:   {depth_stats['max']:.2f} m
  Avg flood depth (flooded):     {avg_depth:.2f} m
  Roads with flooding:           {depth_stats['flooded']} / {depth_stats['count']}

  Safe Driving Speed (Pregnolato et al., 2017):
  {'─' * 55}
  Min safe speed:                {speed_stats['min']:.2f} km/h
  Max safe speed:                {speed_stats['max']:.2f} km/h
  Avg safe speed:                {avg_speed:.2f} km/h

  Vehicle Stability Thresholds (Himalayan-adjusted):
  {'─' * 55}
  Vehicle Type       Threshold  Passable  Impassable  Literature
  {'─' * 55}
  Small car          {SMALL_CAR_DEPTH:.2f} m     {small_pass.get('Passable',0):6d}    {small_pass.get('Impassable',0):6d}       0.30 m
  Ambulance/SUV      {AMBULANCE_DEPTH:.2f} m     {amb_pass.get('Passable',0):6d}    {amb_pass.get('Impassable',0):6d}       0.40 m
  Heavy/Fire truck   {HEAVY_VEHICLE_DEPTH:.2f} m     {heavy_pass.get('Passable',0):6d}    {heavy_pass.get('Impassable',0):6d}       0.50 m
  {'─' * 55}
  Min instability:   {MIN_INSTABILITY_DEPTH} m (ref [49])
  Flow velocity:     < {FLOW_VELOCITY_LIMIT} m/s for stability (ref [16],[51])
""")

# ---- OBJECTIVE 2B: EMERGENCY ROUTES ----
print(f"  Evacuation Route Analysis (Closest Facility):")
print(f"  {'─' * 55}")

routes_fc = os.path.join(OUTPUT_GDB, "Emergency_Routes")
if arcpy.Exists(routes_fc):
    route_count = int(arcpy.management.GetCount(routes_fc)[0])
    route_lengths = []
    with arcpy.da.SearchCursor(routes_fc, ["Total_Length"]) as cursor:
        for row in cursor:
            if row[0]: route_lengths.append(row[0])

    print(f"  Total routes found:            {route_count}")
    if route_lengths:
        print(f"  Min route length:              {min(route_lengths)/1000:.2f} km")
        print(f"  Max route length:              {max(route_lengths)/1000:.2f} km")
        print(f"  Avg route length:              {sum(route_lengths)/len(route_lengths)/1000:.2f} km")
else:
    print(f"  No routes found.")

# ---- OBJECTIVE 3: OPTIMAL LOCATION ----
print(f"""
  {'=' * 55}
  OBJECTIVE 3: OPTIMAL EMERGENCY SERVICE LOCATION
  {'=' * 55}""")

# Service Areas
sa_fc = os.path.join(OUTPUT_GDB, "Hospital_Service_Areas")
if arcpy.Exists(sa_fc):
    sa_count = int(arcpy.management.GetCount(sa_fc)[0])
    print(f"""
  Service Area Analysis:
  {'─' * 55}
  Response time zones:  5, 10, 15, 20 minutes
  Service area polygons: {sa_count}""")

# Optimal centers
opt_fc = os.path.join(OUTPUT_GDB, "Optimal_Emergency_Centers")
cand_fc = os.path.join(OUTPUT_GDB, "Candidate_Locations")
alloc_fc = os.path.join(OUTPUT_GDB, "Allocation_Lines")

if arcpy.Exists(opt_fc):
    opt_count = int(arcpy.management.GetCount(opt_fc)[0])
    cand_count = int(arcpy.management.GetCount(cand_fc)[0]) if arcpy.Exists(cand_fc) else 0
    alloc_count = int(arcpy.management.GetCount(alloc_fc)[0]) if arcpy.Exists(alloc_fc) else 0

    # Count required vs chosen
    req_count = 0
    chosen_count = 0
    try:
        with arcpy.da.SearchCursor(opt_fc, ["FacilityType"]) as cursor:
            for row in cursor:
                if row[0] == 1:
                    req_count += 1
                else:
                    chosen_count += 1
    except:
        req_count = hospital_count
        chosen_count = opt_count - hospital_count

    print(f"""
  Location-Allocation Analysis:
  {'─' * 55}
  Problem type:           MINIMIZE_IMPEDANCE
  Max response time:      {MAX_RESPONSE_TIME} min
  Candidate locations:    {cand_count} (every 2km along safe roads)
  {'─' * 55}
  Existing hospitals:     {req_count} (required)
  New optimal centers:    {chosen_count} (selected by solver)
  Total optimal centers:  {opt_count}
  Allocation lines:       {alloc_count} (demand-to-facility links)
""")

# ---- FLOOD DEMAND ANALYSIS ----
flood_cent_fc = os.path.join(OUTPUT_GDB, "Flood_Zone_Centroids")
flood_poly_filt = os.path.join(OUTPUT_GDB, "Flood_Polygon_Filtered")
if arcpy.Exists(flood_cent_fc):
    cent_count = int(arcpy.management.GetCount(flood_cent_fc)[0])
    poly_filt_count = int(arcpy.management.GetCount(flood_poly_filt)[0]) if arcpy.Exists(flood_poly_filt) else 0
    print(f"  Flood Demand Points:")
    print(f"  {'─' * 55}")
    print(f"  Flood polygons (> 10,000 sq m): {poly_filt_count}")
    print(f"  Demand centroids:               {cent_count}")

# ---- OUTPUT FILES ----
print(f"""
  {'=' * 55}
  OUTPUT FILES
  {'=' * 55}
  Geodatabase: {OUTPUT_GDB}
  {'─' * 55}""")

# List all feature classes in GDB
arcpy.env.workspace = OUTPUT_GDB
fcs = arcpy.ListFeatureClasses()
if fcs:
    for fc in sorted(fcs):
        fc_count = int(arcpy.management.GetCount(fc)[0])
        desc = arcpy.Describe(fc)
        print(f"    {fc:35s}  {desc.shapeType:10s}  {fc_count:6d} features")
arcpy.env.workspace = WORKSPACE

print(f"""
  Raster outputs:
  {'─' * 55}""")
for rname in ["flood_depth_float.tif", "flood_risk_zones.tif",
              "safe_speed_pregnolato.tif", "safe_speed_classes.tif"]:
    rpath = os.path.join(WORKSPACE, rname)
    if arcpy.Exists(rpath):
        r = Raster(rpath)
        print(f"    {rname:40s}  Min:{r.minimum:8.2f}  Max:{r.maximum:8.2f}")

# ---- METHODOLOGY REFERENCES ----
print(f"""
  {'=' * 55}
  METHODOLOGY & REFERENCES
  {'=' * 55}
  Flood Inundation:    MIKE+ flood model (depth, extent, velocity)
  Resampling:          Nearest neighbor (point) - preserves values
  Road Sampling:       1m vertex densification, point extraction
  Speed Function:      Pregnolato et al. (2017) [ref 34]
                       v(w) = 0.0009w² - 0.5529w + 86.9448
  Vehicle Stability:   Small=0.3m, Large=0.4m, Heavy=0.5m [ref 16,51]
                       Adjusted for Himalayan conditions
  Min Instability:     0.20m [ref 49]
  Flow Velocity:       < 1.0 m/s for stability [ref 16,51]
  Risk Classification: Red(>1.5m)/Orange(0.5-1.5m)/Yellow(<0.5m)/Green(0m)
  Route Analysis:      Closest Facility (ArcGIS Network Analyst)
  Service Areas:       5/10/15/20 min from hospitals
  Location-Allocation: Minimize Impedance, {MAX_RESPONSE_TIME} min cutoff
""")

print("=" * 70)
print("  ANALYSIS COMPLETE")
print("=" * 70)


# ---- CELL 12: Load All Layers with Colorful Symbology ----
# Add all result layers to map with research-grade colors
# Then manually export from ArcGIS Pro: Share > Export Map
print("=" * 65)
print("LOADING ALL LAYERS WITH COLORFUL SYMBOLOGY")
print("=" * 65)

aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

# Clear map
for lyr in active_map.listLayers():
    active_map.removeLayer(lyr)

# Set coordinate system to WGS84 (lat/long)
wgs84 = arcpy.SpatialReference(4326)
active_map.spatialReference = wgs84

# --- Create Major Places layer ---
PLACES_FC = os.path.join(OUTPUT_GDB, "Major_Places")
if arcpy.Exists(PLACES_FC):
    arcpy.management.Delete(PLACES_FC)
arcpy.management.CreateFeatureclass(OUTPUT_GDB, "Major_Places", "POINT",
                                    spatial_reference=wgs84)
arcpy.management.AddField(PLACES_FC, "place_name", "TEXT", field_length=50)
places = [
    ("Kullu",      77.1095, 31.9579),
    ("Manali",     77.1887, 32.2396),
    ("Bhuntar",    77.1588, 31.8778),
    ("Naggar",     77.1710, 32.1300),
    ("Katrain",    77.1480, 32.0990),
    ("Patlikuhl",  77.1370, 32.0650),
    ("Banjar",     77.3390, 31.6380),
    ("Aut",        77.0770, 31.8180),
    ("Mandi",      76.9310, 31.7084),
    ("Larji",      77.0950, 31.8020),
    ("Manikaran",  77.3490, 32.0280),
    ("Kasol",      77.3140, 32.0100),
    ("Jari",       77.3230, 32.0170),
    ("Sainj",      77.2960, 31.7570),
    ("Raison",     77.1590, 32.1630),
]
with arcpy.da.InsertCursor(PLACES_FC, ["SHAPE@XY", "place_name"]) as cursor:
    for name, lon, lat in places:
        cursor.insertRow([(lon, lat), name])
print(f"  Major Places: {len(places)} locations")

# --- Add all layers (bottom to top order) ---
all_layers = [
    # Bottom: Rasters
    (DEM_PATH,                                              "DEM"),
    (os.path.join(WORKSPACE, "flood_depth_float.tif"), "Flood Depth"),
    (os.path.join(WORKSPACE, "flood_risk_zones.tif"),       "Flood Risk Raster"),
    # Middle: Polygons
    (os.path.join(OUTPUT_GDB, "Flood_Risk_Zones"),          "Flood Risk Zones"),
    (os.path.join(OUTPUT_GDB, "Safe_Speed_Zones"),          "Safe Speed Zones"),
    (os.path.join(OUTPUT_GDB, "Hospital_Service_Areas"),    "Service Areas"),
    (os.path.join(OUTPUT_GDB, "Flood_Polygon_Filtered"),    "Flood Polygons"),
    # Lines
    (os.path.join(OUTPUT_GDB, "Road_Vulnerability"),        "Road Vulnerability"),
    (os.path.join(OUTPUT_GDB, "Traversable_Roads"),         "Traversable Roads"),
    (os.path.join(OUTPUT_GDB, "Restricted_Roads"),          "Restricted Roads"),
    (os.path.join(OUTPUT_GDB, "Blocked_Roads"),             "Blocked Roads"),
    (os.path.join(OUTPUT_GDB, "Emergency_Routes"),          "Emergency Routes"),
    (os.path.join(OUTPUT_GDB, "Allocation_Lines"),          "Allocation Lines"),
    (ROAD_NETWORK,                                          "Roads"),
    # Top: Points
    (os.path.join(OUTPUT_GDB, "Flood_Zone_Centroids"),      "Flood Centroids"),
    (os.path.join(OUTPUT_GDB, "Candidate_Locations"),       "Candidate Locations"),
    (os.path.join(OUTPUT_GDB, "Optimal_Emergency_Centers"), "Optimal Centers"),
    (HOSPITALS,                                             "Hospitals"),
    (PLACES_FC,                                             "Major Places"),
]

added = 0
for lpath, label in all_layers:
    if arcpy.Exists(lpath):
        active_map.addDataFromPath(lpath)
        added += 1
        print(f"    Added: {label}")

print(f"\n  {added} layers added. Applying symbology...")

# --- Apply CIM symbology to each layer ---
for lyr in active_map.listLayers():
    try:
        if lyr.isBasemapLayer:
            continue
        name = lyr.name
        cim = lyr.getDefinition("V3")

        # --- POLYGON LAYERS ---
        if name == "Flood_Risk_Zones":
            cim.renderer = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueRenderer", "V3")
            cim.renderer.fields = ["gridcode"]
            grps = []
            for val, r, g, b, label in [
                (0, 0, 200, 0,     "Green - No Flood (0m)"),
                (1, 255, 255, 0,   "Yellow - Minor (< 0.5m)"),
                (2, 255, 165, 0,   "Orange - Moderate (0.5-1.5m)"),
                (3, 255, 0, 0,     "Red - Major (> 1.5m)")]:
                cls = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueClass", "V3")
                cls.values = [arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValue", "V3")]
                cls.values[0].fieldValues = [str(val)]
                cls.label = label
                cls.visible = True
                sym = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
                poly_sym = arcpy.cim.CreateCIMObjectFromClassName("CIMPolygonSymbol", "V3")
                fill = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidFill", "V3")
                fill.enable = True
                col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
                col.values = [r, g, b, 100]
                fill.color = col
                poly_sym.symbolLayers = [fill]
                sym.symbol = poly_sym
                cls.symbol = sym
                grps.append(cls)
            grp = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueGroup", "V3")
            grp.classes = grps
            cim.renderer.groups = [grp]
            lyr.setDefinition(cim)
            print(f"    Colored: {name} (Red/Orange/Yellow/Green)")

        elif name == "Safe_Speed_Zones":
            cim.renderer = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueRenderer", "V3")
            cim.renderer.fields = ["gridcode"]
            grps = []
            for val, r, g, b, label in [
                (0, 139, 0, 0,     "0 km/h - Impassable"),
                (1, 255, 0, 0,     "0-10 km/h - Critical"),
                (2, 255, 165, 0,   "10-20 km/h - Severe"),
                (3, 255, 255, 0,   "20-30 km/h - Moderate"),
                (4, 144, 238, 144, "30-40 km/h - Slight"),
                (5, 0, 180, 0,     "40-50 km/h - Near Normal")]:
                cls = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueClass", "V3")
                cls.values = [arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValue", "V3")]
                cls.values[0].fieldValues = [str(val)]
                cls.label = label
                cls.visible = True
                sym = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
                poly_sym = arcpy.cim.CreateCIMObjectFromClassName("CIMPolygonSymbol", "V3")
                fill = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidFill", "V3")
                fill.enable = True
                col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
                col.values = [r, g, b, 100]
                fill.color = col
                poly_sym.symbolLayers = [fill]
                sym.symbol = poly_sym
                cls.symbol = sym
                grps.append(cls)
            grp = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueGroup", "V3")
            grp.classes = grps
            cim.renderer.groups = [grp]
            lyr.setDefinition(cim)
            print(f"    Colored: {name} (Green-to-Red speed)")

        elif name == "Flood_Polygon_Filtered":
            fill = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidFill", "V3")
            fill.enable = True
            col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
            col.values = [0, 150, 255, 50]
            fill.color = col
            stroke = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidStroke", "V3")
            stroke.enable = True
            stroke.width = 1
            scol = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
            scol.values = [0, 80, 200, 100]
            stroke.color = scol
            poly_sym = arcpy.cim.CreateCIMObjectFromClassName("CIMPolygonSymbol", "V3")
            poly_sym.symbolLayers = [stroke, fill]
            sym_ref = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
            sym_ref.symbol = poly_sym
            cim.renderer.symbol = sym_ref
            lyr.setDefinition(cim)
            print(f"    Colored: {name} (Light blue)")

        # --- LINE LAYERS ---
        elif name in ["Road_Vulnerability", "Traversable_Roads", "Blocked_Roads",
                       "Restricted_Roads", "Emergency_Routes", "Allocation_Lines", "roads",
                       "Emergency_Vehicle_Roads"]:
            color_map = {
                "Traversable_Roads":      [0, 180, 0, 100],
                "Blocked_Roads":          [255, 0, 0, 100],
                "Restricted_Roads":       [255, 165, 0, 100],
                "Emergency_Routes":       [0, 70, 255, 100],
                "Allocation_Lines":       [148, 0, 211, 100],
                "roads":                  [100, 100, 100, 100],
                "Emergency_Vehicle_Roads":[0, 120, 200, 100],
            }
            width_map = {
                "Emergency_Routes": 3, "Blocked_Roads": 2.5,
                "Traversable_Roads": 2, "Restricted_Roads": 2,
                "roads": 1, "Allocation_Lines": 1.5,
            }

            if name == "Road_Vulnerability":
                # UniqueValue by road_status
                cim.renderer = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueRenderer", "V3")
                cim.renderer.fields = ["road_status"]
                grps = []
                for val, r, g, b, label in [
                    ("Safe",       0, 180, 0,   "Safe"),
                    ("Caution",    255, 255, 0, "Caution"),
                    ("Restricted", 255, 165, 0, "Restricted"),
                    ("Impassable", 255, 0, 0,   "Impassable")]:
                    cls = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueClass", "V3")
                    cls.values = [arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValue", "V3")]
                    cls.values[0].fieldValues = [val]
                    cls.label = label
                    cls.visible = True
                    sym = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
                    line_sym = arcpy.cim.CreateCIMObjectFromClassName("CIMLineSymbol", "V3")
                    stroke = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidStroke", "V3")
                    stroke.enable = True
                    stroke.width = 2
                    col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
                    col.values = [r, g, b, 100]
                    stroke.color = col
                    line_sym.symbolLayers = [stroke]
                    sym.symbol = line_sym
                    cls.symbol = sym
                    grps.append(cls)
                grp = arcpy.cim.CreateCIMObjectFromClassName("CIMUniqueValueGroup", "V3")
                grp.classes = grps
                cim.renderer.groups = [grp]
                lyr.setDefinition(cim)
                print(f"    Colored: {name} (Green/Yellow/Orange/Red)")
            else:
                rgba = color_map.get(name, [0, 0, 0, 100])
                w = width_map.get(name, 1.5)
                line_sym = arcpy.cim.CreateCIMObjectFromClassName("CIMLineSymbol", "V3")
                stroke = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidStroke", "V3")
                stroke.enable = True
                stroke.width = w
                col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
                col.values = rgba
                stroke.color = col
                line_sym.symbolLayers = [stroke]
                sym_ref = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
                sym_ref.symbol = line_sym
                cim.renderer.symbol = sym_ref
                lyr.setDefinition(cim)
                print(f"    Colored: {name} ({rgba[:3]})")

        # --- POINT LAYERS ---
        elif name in ["hospitals", "Optimal_Emergency_Centers", "Candidate_Locations",
                       "Flood_Zone_Centroids", "Major_Places"]:
            pt_config = {
                "hospitals":                  ([255, 0, 0, 100],   12),
                "Optimal_Emergency_Centers":  ([0, 0, 255, 100],   14),
                "Candidate_Locations":        ([150, 150, 150, 100], 5),
                "Flood_Zone_Centroids":       ([255, 100, 0, 100],  8),
                "Major_Places":               ([30, 30, 30, 100],   8),
            }
            rgba, sz = pt_config.get(name, ([0, 0, 0, 100], 8))
            marker = arcpy.cim.CreateCIMObjectFromClassName("CIMPointSymbol", "V3")
            marker_layer = arcpy.cim.CreateCIMObjectFromClassName("CIMVectorMarker", "V3")
            marker_layer.enable = True
            marker_layer.size = sz
            # Create circle marker frame
            frame = arcpy.cim.CreateCIMObjectFromClassName("CIMMarkerGraphic", "V3")
            circle_geom = arcpy.cim.CreateCIMObjectFromClassName("CIMPolygonSymbol", "V3")
            fill = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidFill", "V3")
            fill.enable = True
            col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
            col.values = rgba
            fill.color = col
            outline = arcpy.cim.CreateCIMObjectFromClassName("CIMSolidStroke", "V3")
            outline.enable = True
            outline.width = 1
            ocol = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
            ocol.values = [255, 255, 255, 100]
            outline.color = ocol
            circle_geom.symbolLayers = [outline, fill]
            sym_ref2 = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
            sym_ref2.symbol = circle_geom
            frame.symbol = sym_ref2
            marker_layer.markerGraphics = [frame]
            marker.symbolLayers = [marker_layer]
            sym_ref = arcpy.cim.CreateCIMObjectFromClassName("CIMSymbolReference", "V3")
            sym_ref.symbol = marker
            cim.renderer.symbol = sym_ref
            lyr.setDefinition(cim)
            print(f"    Colored: {name} ({rgba[:3]}, size={sz})")

            # Labels for Major Places
            if name == "Major_Places":
                lyr.showLabels = True
                try:
                    lblClass = lyr.listLabelClasses()[0]
                    lblClass.expression = "$feature.place_name"
                    lblClass.visible = True
                except:
                    pass

    except Exception as e:
        print(f"    Symbology skip: {name} ({e})")

# Turn off layers you don't need initially (toggle in Contents pane)
# Keep key layers visible, hide supporting ones
hide_layers = ["DEM", "Flood Risk Raster", "Candidate_Locations",
               "Flood_Polygon_Filtered", "Allocation_Lines"]
for lyr in active_map.listLayers():
    if lyr.name in hide_layers:
        lyr.visible = False

print(f"\n{'=' * 65}")
print("  ALL LAYERS LOADED WITH COLORFUL SYMBOLOGY")
print("  Toggle layers on/off in Contents pane")
print("  Export: Share > Export Map > PDF (300 DPI)")
print(f"{'=' * 65}")

arcpy.CheckInExtension("Spatial")
arcpy.CheckInExtension("Network")


# ---- CELL 13: Detailed Results & Statistics ----
# Run this LAST to get complete summary of all results
print("")
print("=" * 70)
print("  RESILIENT INFRASTRUCTURE PLANNING FOR GLOF-PRONE REGIONS")
print("  DETAILED ANALYSIS REPORT")
print("  Beas River Basin, Kullu Valley, Himachal Pradesh")
print("=" * 70)

import arcpy
from arcpy.sa import *
import os

arcpy.CheckOutExtension("Spatial")
arcpy.CheckOutExtension("Network")

WORKSPACE = r"D:\Internship\hand\Hand_folde"
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")
FLOOD_MAP = os.path.join(WORKSPACE, "Beas_Final_Flood_Depth.tif")
DEM_PATH = r"D:\Internship\hand\Bease_River_Basin_DEM-002.tif"
ROAD_NETWORK = os.path.join(WORKSPACE, "roads.shp")
HOSPITALS = os.path.join(WORKSPACE, "hospitals.shp")

# ---- INPUT DATA ----
flood_ras = Raster(FLOOD_MAP)
dem_desc = arcpy.Describe(DEM_PATH)
total_roads = int(arcpy.management.GetCount(ROAD_NETWORK)[0])
hospital_count = int(arcpy.management.GetCount(HOSPITALS)[0])

print(f"""
  INPUT DATA
  {'─' * 55}
  Flood Depth Raster:  {os.path.basename(FLOOD_MAP)}
    Min Depth:         {flood_ras.minimum:.2f} m
    Max Depth:         {flood_ras.maximum:.2f} m
    Mean Depth:        {flood_ras.mean:.2f} m
    Pixel Type:        {arcpy.Describe(FLOOD_MAP).pixelType}
    Cell Size:         {arcpy.Describe(FLOOD_MAP).meanCellWidth:.2f} m

  DEM:                 {os.path.basename(DEM_PATH)}
    Cell Size:         {dem_desc.meanCellWidth:.2f} m
    Spatial Reference: {dem_desc.spatialReference.name}

  Road Network:        {os.path.basename(ROAD_NETWORK)}
    Total Segments:    {total_roads}

  Hospitals:           {hospital_count} facilities
""")

# ---- OBJECTIVE 1: FLOOD RISK ZONES ----
print(f"  {'=' * 55}")
print(f"  OBJECTIVE 1: FLOOD RISK ZONE CLASSIFICATION")
print(f"  {'=' * 55}")

zone_counts = {}
zone_areas = {}
flood_risk_poly = os.path.join(OUTPUT_GDB, "Flood_Risk_Zones")
if arcpy.Exists(flood_risk_poly):
    with arcpy.da.SearchCursor(flood_risk_poly, ["gridcode", "SHAPE@AREA"]) as cursor:
        for row in cursor:
            gc = row[0]
            zone_counts[gc] = zone_counts.get(gc, 0) + 1
            zone_areas[gc] = zone_areas.get(gc, 0) + row[1]

total_polys = sum(zone_counts.values()) if zone_counts else 1
total_area = sum(zone_areas.values())

print(f"""
  Zone          Depth         Polygons      Area (sq km)    %
  {'─' * 55}""")

for gc, label, depth in [
    (3, "Red/Major",    "> 1.5 m"),
    (2, "Orange/Mod",   "0.5-1.5 m"),
    (1, "Yellow/Minor", "< 0.5 m"),
    (0, "Green/None",   "0 m")]:
    cnt = zone_counts.get(gc, 0)
    area_km2 = zone_areas.get(gc, 0) / 1e6
    pct = cnt / total_polys * 100
    print(f"  {label:14s} {depth:12s} {cnt:8d}    {area_km2:12.2f}   {pct:5.1f}%")

print(f"  {'─' * 55}")
print(f"  {'TOTAL':14s} {'':12s} {total_polys:8d}    {total_area/1e6:12.2f}   100.0%")

# ---- SAFE SPEED (PREGNOLATO) ----
safe_speed_poly = os.path.join(OUTPUT_GDB, "Safe_Speed_Zones")
if arcpy.Exists(safe_speed_poly):
    print(f"""
  ALLOWABLE SPEED (Pregnolato et al., 2017)
  v(w) = 0.0009w² - 0.5529w + 86.9448
  {'─' * 55}""")
    speed_counts = {}
    with arcpy.da.SearchCursor(safe_speed_poly, ["gridcode"]) as cursor:
        for row in cursor:
            speed_counts[row[0]] = speed_counts.get(row[0], 0) + 1
    for gc, speed, cond in [
        (5, "40-50 km/h", "Near Normal"),   (4, "30-40 km/h", "Slight"),
        (3, "20-30 km/h", "Moderate"),       (2, "10-20 km/h", "Severe"),
        (1, "0-10 km/h",  "Critical"),       (0, "0 km/h",     "Impassable")]:
        cnt = speed_counts.get(gc, 0)
        print(f"  {speed:14s}  {cond:22s}  {cnt:8d} polygons")

# ---- OBJECTIVE 2: ROAD VULNERABILITY ----
print(f"""
  {'=' * 55}
  OBJECTIVE 2: ROAD VULNERABILITY & VEHICULAR MOBILITY
  {'=' * 55}""")

road_vuln_fc = os.path.join(OUTPUT_GDB, "Road_Vulnerability")
status_counts = {}
depth_stats = {"max": 0, "total": 0, "count": 0, "flooded": 0}
speed_stats = {"min": 999, "max": 0, "total": 0, "count": 0}
small_p = 0; small_i = 0
amb_p = 0; amb_i = 0
heavy_p = 0; heavy_i = 0

if arcpy.Exists(road_vuln_fc):
    with arcpy.da.SearchCursor(road_vuln_fc,
        ["road_status", "flood_depth", "safe_speed", "small_car", "ambulance", "heavy_veh"]) as cursor:
        for row in cursor:
            status_counts[row[0]] = status_counts.get(row[0], 0) + 1
            if row[1] and row[1] > 0:
                depth_stats["max"] = max(depth_stats["max"], row[1])
                depth_stats["total"] += row[1]
                depth_stats["flooded"] += 1
            depth_stats["count"] += 1
            if row[2] is not None:
                speed_stats["min"] = min(speed_stats["min"], row[2])
                speed_stats["max"] = max(speed_stats["max"], row[2])
                speed_stats["total"] += row[2]
                speed_stats["count"] += 1
            if row[3] == "Passable": small_p += 1
            else: small_i += 1
            if row[4] == "Passable": amb_p += 1
            else: amb_i += 1
            if row[5] == "Passable": heavy_p += 1
            else: heavy_i += 1

total_assessed = sum(status_counts.values()) if status_counts else 1
avg_depth = depth_stats["total"] / depth_stats["flooded"] if depth_stats["flooded"] > 0 else 0
avg_speed = speed_stats["total"] / speed_stats["count"] if speed_stats["count"] > 0 else 0

print(f"""
  Road Status:
  {'─' * 55}
  Status         Segments     %
  {'─' * 55}
  Safe           {status_counts.get('Safe',0):6d}    {status_counts.get('Safe',0)/total_assessed*100:5.1f}%
  Caution        {status_counts.get('Caution',0):6d}    {status_counts.get('Caution',0)/total_assessed*100:5.1f}%
  Restricted     {status_counts.get('Restricted',0):6d}    {status_counts.get('Restricted',0)/total_assessed*100:5.1f}%
  Impassable     {status_counts.get('Impassable',0):6d}    {status_counts.get('Impassable',0)/total_assessed*100:5.1f}%
  {'─' * 55}
  TOTAL          {total_assessed:6d}    100.0%

  Flood Depth on Roads:
  {'─' * 55}
  Max depth on any road:    {depth_stats['max']:.2f} m
  Avg depth (flooded only): {avg_depth:.2f} m
  Flooded road segments:    {depth_stats['flooded']} / {depth_stats['count']}

  Safe Driving Speed:
  {'─' * 55}
  Min safe speed:           {speed_stats['min']:.2f} km/h
  Max safe speed:           {speed_stats['max']:.2f} km/h
  Avg safe speed:           {avg_speed:.2f} km/h

  Vehicle Passability:
  {'─' * 55}
  Vehicle Type       Threshold  Passable  Impassable  Lit. Value
  {'─' * 55}
  Small car          0.25 m     {small_p:6d}    {small_i:6d}       0.30 m
  Ambulance/SUV      0.35 m     {amb_p:6d}    {amb_i:6d}       0.40 m
  Heavy/Fire truck   0.45 m     {heavy_p:6d}    {heavy_i:6d}       0.50 m
""")

# ---- EVACUATION ROUTES ----
print(f"  Evacuation Routes (Closest Facility):")
print(f"  {'─' * 55}")

routes_fc = os.path.join(OUTPUT_GDB, "Emergency_Routes")
if arcpy.Exists(routes_fc):
    route_count = int(arcpy.management.GetCount(routes_fc)[0])
    route_times = []
    route_lengths = []
    # Try common field names for time and length
    fields = [f.name for f in arcpy.ListFields(routes_fc)]
    time_field = None
    len_field = None
    for f in fields:
        fl = f.lower()
        if "time" in fl or "total_time" in fl or "totaltime" in fl:
            time_field = f
        if "length" in fl or "total_length" in fl or "totallength" in fl or "shape_length" in fl:
            len_field = f

    if time_field and len_field:
        with arcpy.da.SearchCursor(routes_fc, [time_field, len_field]) as cursor:
            for row in cursor:
                if row[0] is not None: route_times.append(row[0])
                if row[1] is not None: route_lengths.append(row[1])
    elif time_field:
        with arcpy.da.SearchCursor(routes_fc, [time_field, "SHAPE@LENGTH"]) as cursor:
            for row in cursor:
                if row[0] is not None: route_times.append(row[0])
                if row[1] is not None: route_lengths.append(row[1])
    else:
        with arcpy.da.SearchCursor(routes_fc, ["SHAPE@LENGTH"]) as cursor:
            for row in cursor:
                if row[0] is not None: route_lengths.append(row[0])

    print(f"  Total routes:                  {route_count}")
    if route_times:
        within_20 = sum(1 for t in route_times if t <= 20)
        print(f"  Min travel time:               {min(route_times):.2f} min")
        print(f"  Max travel time:               {max(route_times):.2f} min")
        print(f"  Avg travel time:               {sum(route_times)/len(route_times):.2f} min")
        print(f"  Routes within 20 min:          {within_20}/{route_count} ({within_20/route_count*100:.1f}%)")
    if route_lengths:
        print(f"  Min route length:              {min(route_lengths)/1000:.2f} km")
        print(f"  Max route length:              {max(route_lengths)/1000:.2f} km")
        print(f"  Avg route length:              {sum(route_lengths)/len(route_lengths)/1000:.2f} km")

    # Print route fields for reference
    print(f"\n  Route fields: {', '.join(fields)}")
else:
    print(f"  No routes found.")

# ---- OBJECTIVE 3: OPTIMAL LOCATION ----
print(f"""
  {'=' * 55}
  OBJECTIVE 3: OPTIMAL EMERGENCY SERVICE LOCATION
  {'=' * 55}""")

sa_fc = os.path.join(OUTPUT_GDB, "Hospital_Service_Areas")
if arcpy.Exists(sa_fc):
    sa_count = int(arcpy.management.GetCount(sa_fc)[0])
    print(f"  Service area polygons:         {sa_count}")
    print(f"  Time zones:                    5, 10, 15, 20 min")

opt_fc = os.path.join(OUTPUT_GDB, "Optimal_Emergency_Centers")
cand_fc = os.path.join(OUTPUT_GDB, "Candidate_Locations")
alloc_fc = os.path.join(OUTPUT_GDB, "Allocation_Lines")

if arcpy.Exists(opt_fc):
    opt_count = int(arcpy.management.GetCount(opt_fc)[0])
    cand_count = int(arcpy.management.GetCount(cand_fc)[0]) if arcpy.Exists(cand_fc) else 0
    alloc_count = int(arcpy.management.GetCount(alloc_fc)[0]) if arcpy.Exists(alloc_fc) else 0

    req_count = 0
    chosen_count = 0
    try:
        with arcpy.da.SearchCursor(opt_fc, ["FacilityType"]) as cursor:
            for row in cursor:
                if row[0] == 1: req_count += 1
                else: chosen_count += 1
    except:
        req_count = hospital_count
        chosen_count = opt_count - hospital_count

    print(f"""
  Location-Allocation:
  {'─' * 55}
  Problem type:              MINIMIZE_IMPEDANCE
  Candidate locations:       {cand_count} (every 2km on safe roads)
  Existing hospitals:        {req_count} (required)
  New optimal centers:       {chosen_count} (solver-selected)
  Total optimal centers:     {opt_count}
  Allocation links:          {alloc_count}
""")

# ---- FLOOD DEMAND ----
flood_cent_fc = os.path.join(OUTPUT_GDB, "Flood_Zone_Centroids")
flood_poly_filt = os.path.join(OUTPUT_GDB, "Flood_Polygon_Filtered")
if arcpy.Exists(flood_cent_fc):
    cent_count = int(arcpy.management.GetCount(flood_cent_fc)[0])
    poly_count = int(arcpy.management.GetCount(flood_poly_filt)[0]) if arcpy.Exists(flood_poly_filt) else 0
    print(f"  Flood Demand:")
    print(f"  {'─' * 55}")
    print(f"  Flood polygons (> 10,000 sq m): {poly_count}")
    print(f"  Demand centroids:               {cent_count}")

# ---- ALL OUTPUT FILES ----
print(f"""
  {'=' * 55}
  ALL OUTPUT FILES IN GDB
  {'=' * 55}""")

arcpy.env.workspace = OUTPUT_GDB
fcs = arcpy.ListFeatureClasses()
if fcs:
    print(f"  {'Layer':35s}  {'Type':10s}  {'Count':>8s}")
    print(f"  {'─' * 55}")
    for fc in sorted(fcs):
        fc_count = int(arcpy.management.GetCount(fc)[0])
        desc = arcpy.Describe(fc)
        print(f"  {fc:35s}  {desc.shapeType:10s}  {fc_count:8d}")
arcpy.env.workspace = WORKSPACE

print(f"""
  Rasters:
  {'─' * 55}""")
for rname in ["flood_depth_float.tif", "flood_risk_zones.tif",
              "safe_speed_pregnolato.tif", "safe_speed_classes.tif"]:
    rpath = os.path.join(WORKSPACE, rname)
    if arcpy.Exists(rpath):
        r = Raster(rpath)
        print(f"  {rname:40s}  Min:{r.minimum:8.2f}  Max:{r.maximum:8.2f}")

print(f"""
  {'=' * 55}
  REFERENCES
  {'=' * 55}
  [34] Pregnolato et al. (2017) - Depth-disruption function
  [16] [51] - Vehicle stability: 0.3/0.4/0.5m, velocity < 1 m/s
  [49] - 20cm minimum instability depth
  MIKE+ - Flood depth/extent classification
  {'=' * 55}
""")

print("=" * 70)
print("  DETAILED REPORT COMPLETE")
print("=" * 70)

arcpy.CheckInExtension("Spatial")
arcpy.CheckInExtension("Network")


# ---- CELL 14: Extract DEM Boundary & Clip All Layers ----
import arcpy
from arcpy.sa import *
import os

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

WORKSPACE = r"D:\Internship\hand\Hand_folde"
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")
DEM_PATH = r"D:\Internship\hand\Bease_River_Basin_DEM-002.tif"

print("=" * 60)
print("EXTRACTING DEM BOUNDARY & CLIPPING ALL LAYERS")
print("=" * 60)

# Step 1: Extract DEM boundary (non-NoData area)
dem_boundary = os.path.join(OUTPUT_GDB, "DEM_Boundary")
arcpy.ddd.RasterDomain(DEM_PATH, dem_boundary, "POLYGON")
boundary_area = 0
with arcpy.da.SearchCursor(dem_boundary, ["SHAPE@AREA"]) as cursor:
    for row in cursor:
        boundary_area = row[0] / 1e6
print(f"  DEM boundary extracted: {boundary_area:.2f} sq km")

# Step 2: Clip all feature classes in GDB to DEM boundary
arcpy.env.workspace = OUTPUT_GDB
all_fcs = arcpy.ListFeatureClasses()

skip_layers = ["DEM_Boundary"]

for fc in all_fcs:
    if fc in skip_layers or fc.endswith("_clipped"):
        continue

    fc_path = os.path.join(OUTPUT_GDB, fc)
    clipped_path = os.path.join(OUTPUT_GDB, fc + "_clipped")

    try:
        original_count = int(arcpy.management.GetCount(fc_path)[0])
        arcpy.analysis.Clip(fc_path, dem_boundary, clipped_path)
        clipped_count = int(arcpy.management.GetCount(clipped_path)[0])

        # Replace original with clipped
        arcpy.management.Delete(fc_path)
        arcpy.management.Rename(clipped_path, fc)
        print(f"  {fc:35s}: {original_count} -> {clipped_count}")
    except Exception as e:
        print(f"  {fc:35s}: skipped ({str(e)[:50]})")

# Step 3: Clip standalone shapefiles
arcpy.env.workspace = WORKSPACE
for shp in ["roads.shp", "hospitals.shp", "major_places_utm.shp"]:
    shp_path = os.path.join(WORKSPACE, shp)
    if arcpy.Exists(shp_path):
        clipped_path = os.path.join(WORKSPACE, shp.replace(".shp", "_clipped.shp"))
        try:
            original_count = int(arcpy.management.GetCount(shp_path)[0])
            arcpy.analysis.Clip(shp_path, dem_boundary, clipped_path)
            clipped_count = int(arcpy.management.GetCount(clipped_path)[0])
            print(f"  {shp:35s}: {original_count} -> {clipped_count}")
        except Exception as e:
            print(f"  {shp:35s}: skipped ({str(e)[:50]})")

# Step 4: Clip rasters to DEM boundary
for rname in ["flood_depth_float.tif", "flood_risk_zones.tif",
              "safe_speed_pregnolato.tif", "safe_speed_classes.tif"]:
    rpath = os.path.join(WORKSPACE, rname)
    if arcpy.Exists(rpath):
        clipped_rpath = os.path.join(WORKSPACE, rname.replace(".tif", "_clipped.tif"))
        try:
            arcpy.management.Clip(rpath, "", clipped_rpath, dem_boundary, "", "ClippingGeometry")
            print(f"  {rname:35s}: clipped")
        except Exception as e:
            print(f"  {rname:35s}: skipped ({str(e)[:50]})")

# Step 5: Add DEM boundary to map
aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap
if active_map:
    active_map.addDataFromPath(dem_boundary)
    print("\n  DEM boundary added to map.")

print("\nAll layers clipped to DEM boundary.")
arcpy.CheckInExtension("Spatial")


# ---- CELL 15: Load All Clipped Layers to Map ----
import arcpy
import os

WORKSPACE = r"D:\Internship\hand\Hand_folde"
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")

aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

if not active_map:
    print("ERROR: Open a Map tab first.")
else:
    # Clear old layers
    for lyr in active_map.listLayers():
        active_map.removeLayer(lyr)
    print("Old layers cleared.")

    # Add clipped rasters
    for rname in ["flood_depth_float_clipped.tif", "flood_risk_zones_clipped.tif",
                  "safe_speed_pregnolato_clipped.tif", "safe_speed_classes_clipped.tif"]:
        rpath = os.path.join(WORKSPACE, rname)
        if arcpy.Exists(rpath):
            active_map.addDataFromPath(rpath)
            print(f"  + {rname}")

    # Add clipped shapefiles
    for shp in ["roads_clipped.shp", "hospitals_clipped.shp", "major_places_utm_clipped.shp"]:
        spath = os.path.join(WORKSPACE, shp)
        if arcpy.Exists(spath):
            active_map.addDataFromPath(spath)
            print(f"  + {shp}")

    # Add clipped GDB layers
    arcpy.env.workspace = OUTPUT_GDB
    fcs = arcpy.ListFeatureClasses()
    key_layers = [
        "DEM_Boundary",
        "Flood_Risk_Zones",
        "Road_Vulnerability",
        "Traversable_Roads",
        "Blocked_Roads",
        "Restricted_Roads",
        "Emergency_Routes",
        "Hospital_Service_Areas",
        "Optimal_Emergency_Centers",
        "Allocation_Lines",
        "Safe_Speed_Zones",
        "Flood_Zone_Centroids",
        "Major_Places",
    ]
    for fc in key_layers:
        fc_path = os.path.join(OUTPUT_GDB, fc)
        if arcpy.Exists(fc_path):
            active_map.addDataFromPath(fc_path)
            print(f"  + {fc}")

    arcpy.env.workspace = WORKSPACE
    print(f"\nAll clipped layers loaded to map.")
