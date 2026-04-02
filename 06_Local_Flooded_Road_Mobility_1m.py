"""
Create a local flooded-road mobility map at 1 m resolution.

This script is meant to be run in ArcGIS Pro AFTER:
1. 01_HAND_Flood_Mapping.py
2. 02_Download_Data.py
3. 03_Emergency_Routing.py

What it does:
- selects only roads intersecting the modeled flood extent,
- densifies them to 1 m,
- creates 1 m road micro-segments,
- samples flood depth at each micro-segment midpoint,
- applies the depth-disruption function locally,
- creates a map-ready output for flooded road locations.
"""

import os

import arcpy
from arcpy.sa import Con, Raster


arcpy.env.overwriteOutput = True

WORKSPACE = r"D:\Internship\hand\Hand_folde"
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")

FLOOD_RASTER = os.path.join(WORKSPACE, "flood_depth_float.tif")
FINAL_FLOOD_RASTER = os.path.join(WORKSPACE, "Beas_Final_Flood_Depth.tif")
ROAD_NETWORK = os.path.join(WORKSPACE, "roads.shp")
ROAD_VULN = os.path.join(OUTPUT_GDB, "Road_Vulnerability")

FLOOD_POLYGON = os.path.join(OUTPUT_GDB, "Flood_Polygon")
ROADS_IN_FLOOD_ZONE = os.path.join(OUTPUT_GDB, "Roads_In_Flood_Zone")
SOURCE_1M = os.path.join(OUTPUT_GDB, "Roads_In_Flood_Zone_1m_Source")
LOCAL_ROAD_1M = os.path.join(OUTPUT_GDB, "Road_Local_Mobility_1m")
LOCAL_ROAD_1M_PTS = os.path.join(OUTPUT_GDB, "Road_Local_Mobility_1m_Pts")
FLOODED_LOCAL_ROAD_1M = os.path.join(OUTPUT_GDB, "Flooded_Road_Local_Mobility_1m")


SMALL_CAR_DEPTH = 0.25
AMBULANCE_DEPTH = 0.35
HEAVY_VEHICLE_DEPTH = 0.45
MIN_INSTABILITY_DEPTH = 0.20


def delete_if_exists(path):
    if arcpy.Exists(path):
        arcpy.management.Delete(path)


def depth_disruption_speed(depth_m):
    """
    Pregnolato et al. (2017) depth-disruption function.
    Depth in meters, speed in km/h.
    """
    if depth_m is None or depth_m <= 0:
        return 86.94

    if depth_m > 0.30:
        return 0.00

    depth_mm = depth_m * 1000.0
    speed = 0.0009 * (depth_mm ** 2) - 0.5529 * depth_mm + 86.9448
    speed = max(speed, 0.00)
    speed = min(speed, 86.94)
    return round(speed, 2)


def speed_class(speed_kmh):
    if speed_kmh <= 0:
        return 0, "0 km/h"
    if speed_kmh < 10:
        return 1, "0-10 km/h"
    if speed_kmh < 20:
        return 2, "10-20 km/h"
    if speed_kmh < 40:
        return 3, "20-40 km/h"
    if speed_kmh < 60:
        return 4, "40-60 km/h"
    return 5, "60-87 km/h"


def local_status(depth_m, safe_speed):
    if safe_speed <= 0:
        return "Impassable"
    if depth_m <= 0:
        return "Safe"
    if depth_m < MIN_INSTABILITY_DEPTH:
        return "Caution"
    return "Restricted"


def midpoint_from_points(p1, p2, spatial_ref):
    mid_x = (p1.X + p2.X) / 2.0
    mid_y = (p1.Y + p2.Y) / 2.0
    return arcpy.PointGeometry(arcpy.Point(mid_x, mid_y), spatial_ref)


print("=" * 70)
print("LOCAL FLOODED ROAD MOBILITY MAPPING AT 1 M RESOLUTION")
print("=" * 70)

arcpy.CheckOutExtension("Spatial")

# ---------------------------------------------------------------------------
# 1. Choose the best available road input
# ---------------------------------------------------------------------------
if arcpy.Exists(ROAD_VULN):
    road_input = ROAD_VULN
    print("Using Road_Vulnerability as source roads.")
elif arcpy.Exists(ROAD_NETWORK):
    road_input = ROAD_NETWORK
    print("Road_Vulnerability not found. Falling back to roads.shp.")
else:
    raise RuntimeError("No suitable road input found. Run 02_Download_Data.py and 03_Emergency_Routing.py first.")

if arcpy.Exists(FLOOD_RASTER):
    flood_input = FLOOD_RASTER
    print("Using flood_depth_float.tif for local flood depth sampling.")
elif arcpy.Exists(FINAL_FLOOD_RASTER):
    flood_input = FINAL_FLOOD_RASTER
    print("Float flood raster not found. Falling back to Beas_Final_Flood_Depth.tif.")
else:
    raise RuntimeError("No flood raster found. Run 01_HAND_Flood_Mapping.py and 03_Emergency_Routing.py first.")


# ---------------------------------------------------------------------------
# 2. Create or refresh flood polygon
# ---------------------------------------------------------------------------
if not arcpy.Exists(FLOOD_POLYGON):
    print("Creating Flood_Polygon from flood raster...")
    flood_extent = Con(Raster(flood_input) > 0, 1, 0)
    arcpy.conversion.RasterToPolygon(flood_extent, FLOOD_POLYGON, "SIMPLIFY", "VALUE")
else:
    print("Using existing Flood_Polygon.")


# ---------------------------------------------------------------------------
# 3. Select only roads intersecting the flood extent
# ---------------------------------------------------------------------------
delete_if_exists(ROADS_IN_FLOOD_ZONE)

road_layer = "road_input_lyr"
arcpy.management.MakeFeatureLayer(road_input, road_layer)
arcpy.management.SelectLayerByLocation(road_layer, "INTERSECT", FLOOD_POLYGON)
arcpy.management.CopyFeatures(road_layer, ROADS_IN_FLOOD_ZONE)

selected_road_count = int(arcpy.management.GetCount(ROADS_IN_FLOOD_ZONE)[0])
print(f"Roads intersecting flood extent: {selected_road_count}")

if selected_road_count == 0:
    raise RuntimeError("No roads intersect the flood extent. Nothing to segment at 1 m.")


# ---------------------------------------------------------------------------
# 4. Densify selected roads to 1 m
# ---------------------------------------------------------------------------
delete_if_exists(SOURCE_1M)
arcpy.management.CopyFeatures(ROADS_IN_FLOOD_ZONE, SOURCE_1M)
print("Densifying selected roads to 1 meter...")
arcpy.edit.Densify(SOURCE_1M, "DISTANCE", "1 Meters")


# ---------------------------------------------------------------------------
# 5. Create 1 m micro-segments and midpoint sampling points
# ---------------------------------------------------------------------------
for path in [LOCAL_ROAD_1M, LOCAL_ROAD_1M_PTS, FLOODED_LOCAL_ROAD_1M]:
    delete_if_exists(path)

spatial_ref = arcpy.Describe(SOURCE_1M).spatialReference

arcpy.management.CreateFeatureclass(
    OUTPUT_GDB,
    os.path.basename(LOCAL_ROAD_1M),
    "POLYLINE",
    spatial_reference=spatial_ref,
)
for field_name, field_type, field_len in [
    ("seg_uid", "LONG", None),
    ("parent_oid", "LONG", None),
    ("seg_no", "LONG", None),
    ("seg_len_m", "DOUBLE", None),
    ("flood_depth", "DOUBLE", None),
    ("safe_speed", "DOUBLE", None),
    ("speed_rank", "SHORT", None),
    ("speed_class", "TEXT", 20),
    ("local_status", "TEXT", 15),
    ("small_car", "TEXT", 12),
    ("ambulance", "TEXT", 12),
    ("heavy_veh", "TEXT", 12),
    ("flood_flag", "TEXT", 12),
]:
    if field_len:
        arcpy.management.AddField(LOCAL_ROAD_1M, field_name, field_type, field_length=field_len)
    else:
        arcpy.management.AddField(LOCAL_ROAD_1M, field_name, field_type)

arcpy.management.CreateFeatureclass(
    OUTPUT_GDB,
    os.path.basename(LOCAL_ROAD_1M_PTS),
    "POINT",
    spatial_reference=spatial_ref,
)
for field_name, field_type in [
    ("seg_uid", "LONG"),
    ("parent_oid", "LONG"),
    ("seg_no", "LONG"),
]:
    arcpy.management.AddField(LOCAL_ROAD_1M_PTS, field_name, field_type)

segment_count = 0
with arcpy.da.InsertCursor(
    LOCAL_ROAD_1M,
    ["SHAPE@", "seg_uid", "parent_oid", "seg_no", "seg_len_m"],
) as seg_cur, arcpy.da.InsertCursor(
    LOCAL_ROAD_1M_PTS,
    ["SHAPE@", "seg_uid", "parent_oid", "seg_no"],
) as pt_cur, arcpy.da.SearchCursor(
    SOURCE_1M,
    ["OID@", "SHAPE@"],
) as src_cur:
    for parent_oid, geom in src_cur:
        seg_no = 0
        for part in geom:
            previous_point = None
            for point in part:
                if point is None:
                    previous_point = None
                    continue

                if previous_point is not None:
                    segment_geom = arcpy.Polyline(
                        arcpy.Array([previous_point, point]),
                        spatial_ref,
                    )
                    segment_length = segment_geom.length

                    if segment_length > 0:
                        segment_count += 1
                        seg_no += 1
                        mid_geom = midpoint_from_points(previous_point, point, spatial_ref)

                        seg_cur.insertRow([
                            segment_geom,
                            segment_count,
                            parent_oid,
                            seg_no,
                            round(segment_length, 3),
                        ])
                        pt_cur.insertRow([
                            mid_geom,
                            segment_count,
                            parent_oid,
                            seg_no,
                        ])

                previous_point = point

print(f"Created {segment_count} local road micro-segments.")

if segment_count == 0:
    raise RuntimeError("No 1 m micro-segments were created.")


# ---------------------------------------------------------------------------
# 6. Sample flood depth at each 1 m midpoint
# ---------------------------------------------------------------------------
print("Sampling local flood depth at each 1 m midpoint...")
arcpy.sa.ExtractMultiValuesToPoints(
    LOCAL_ROAD_1M_PTS,
    [[flood_input, "fld_depth"]],
    "NONE",
)


# ---------------------------------------------------------------------------
# 7. Transfer sampled depth to segments and compute local mobility fields
# ---------------------------------------------------------------------------
depth_lookup = {}
with arcpy.da.SearchCursor(LOCAL_ROAD_1M_PTS, ["seg_uid", "fld_depth"]) as cursor:
    for seg_uid, flood_depth in cursor:
        if flood_depth is None or flood_depth < 0:
            flood_depth = 0.0
        flood_depth = round(float(flood_depth), 2)
        safe_speed = depth_disruption_speed(flood_depth)
        rank, label = speed_class(safe_speed)
        depth_lookup[seg_uid] = {
            "flood_depth": flood_depth,
            "safe_speed": safe_speed,
            "speed_rank": rank,
            "speed_class": label,
            "local_status": local_status(flood_depth, safe_speed),
            "small_car": "Passable" if flood_depth < SMALL_CAR_DEPTH else "Impassable",
            "ambulance": "Passable" if flood_depth < AMBULANCE_DEPTH else "Impassable",
            "heavy_veh": "Passable" if flood_depth < HEAVY_VEHICLE_DEPTH else "Impassable",
            "flood_flag": "Flooded" if flood_depth > 0 else "Dry",
        }

print("Updating 1 m segments with local depth and speed...")
with arcpy.da.UpdateCursor(
    LOCAL_ROAD_1M,
    [
        "seg_uid",
        "flood_depth",
        "safe_speed",
        "speed_rank",
        "speed_class",
        "local_status",
        "small_car",
        "ambulance",
        "heavy_veh",
        "flood_flag",
    ],
) as cursor:
    for row in cursor:
        info = depth_lookup.get(row[0], None)
        if info is None:
            continue

        row[1] = info["flood_depth"]
        row[2] = info["safe_speed"]
        row[3] = info["speed_rank"]
        row[4] = info["speed_class"]
        row[5] = info["local_status"]
        row[6] = info["small_car"]
        row[7] = info["ambulance"]
        row[8] = info["heavy_veh"]
        row[9] = info["flood_flag"]
        cursor.updateRow(row)


# ---------------------------------------------------------------------------
# 8. Create flooded-only output for cleaner mapping
# ---------------------------------------------------------------------------
print("Creating flooded-only 1 m mobility layer...")
arcpy.analysis.Select(LOCAL_ROAD_1M, FLOODED_LOCAL_ROAD_1M, "flood_depth > 0")

flooded_segment_count = int(arcpy.management.GetCount(FLOODED_LOCAL_ROAD_1M)[0])
print(f"Flooded 1 m segments: {flooded_segment_count}")


# ---------------------------------------------------------------------------
# 9. Summary statistics
# ---------------------------------------------------------------------------
speed_counts = {
    "60-87 km/h": 0,
    "40-60 km/h": 0,
    "20-40 km/h": 0,
    "10-20 km/h": 0,
    "0-10 km/h": 0,
    "0 km/h": 0,
}
speed_lengths = dict((k, 0.0) for k in speed_counts)

with arcpy.da.SearchCursor(FLOODED_LOCAL_ROAD_1M, ["speed_class", "seg_len_m"]) as cursor:
    for speed_label, seg_len_m in cursor:
        if speed_label in speed_counts:
            speed_counts[speed_label] += 1
            speed_lengths[speed_label] += (seg_len_m or 0.0) / 1000.0

print("")
print("Local flooded-road mobility summary (1 m segments):")
for label in ["60-87 km/h", "40-60 km/h", "20-40 km/h", "10-20 km/h", "0-10 km/h", "0 km/h"]:
    print(f"  {label:12s} : {speed_counts[label]:8d} segments | {speed_lengths[label]:8.3f} km")


# ---------------------------------------------------------------------------
# 10. Add outputs to active ArcGIS map
# ---------------------------------------------------------------------------
aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

if active_map:
    for lyr in active_map.listLayers():
        if lyr.name in ("Road_Local_Mobility_1m", "Flooded_Road_Local_Mobility_1m", "Roads_In_Flood_Zone"):
            active_map.removeLayer(lyr)

    active_map.addDataFromPath(ROADS_IN_FLOOD_ZONE)
    active_map.addDataFromPath(FLOODED_LOCAL_ROAD_1M)
    print("Added Roads_In_Flood_Zone and Flooded_Road_Local_Mobility_1m to the current map.")
    print("Recommended symbology: Unique Values on field 'speed_class'.")
else:
    print("No active map found. Open a map in ArcGIS Pro to auto-add the outputs.")

print("")
print("=" * 70)
print("1 M LOCAL FLOODED ROAD MOBILITY ANALYSIS COMPLETE")
print("=" * 70)
print(f"All local 1 m segments: {LOCAL_ROAD_1M}")
print(f"Flooded-only 1 m segments: {FLOODED_LOCAL_ROAD_1M}")
print(f"Midpoint sample points: {LOCAL_ROAD_1M_PTS}")

arcpy.CheckInExtension("Spatial")
