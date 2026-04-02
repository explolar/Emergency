# =============================================================================
# CELL 1: HAND Dual-Stage Flood Inundation Mapping
# Paste each section into a separate ArcGIS Pro Notebook cell
# =============================================================================

# ---- CELL 1: Setup & Parameters ----
import arcpy
from arcpy.sa import *
import os

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

# Project workspace
WORKSPACE = r"D:\Internship\hand\Hand_folde"
arcpy.env.workspace = WORKSPACE
arcpy.env.compression = "LZW"
arcpy.env.parallelProcessingFactor = "100%"

# Input DEM
RAW_DEM = os.path.join(WORKSPACE, "Bease_River_Basin_DEM-002.tif")

# Output
FINAL_FLOOD_MAP = os.path.join(WORKSPACE, "Beas_Final_Flood_Depth.tif")

# Thresholds for 2.5m Cartosat DEM
TRIB_THRESHOLD = 160000
MAIN_THRESHOLD = 1500000

# Water levels from literature
TRIB_WATER_LEVEL = 5.0
MAIN_WATER_LEVEL = 12.0

arcpy.AddMessage("Setup complete. Workspace: " + WORKSPACE)
arcpy.AddMessage("DEM: " + RAW_DEM)

# ---- CELL 2: Hydrology Processing ----
arcpy.AddMessage("Step 1: Filling sinks in DEM...")
filled_dem = Fill(RAW_DEM)
filled_dem.save(os.path.join(WORKSPACE, "filled_dem.tif"))
arcpy.AddMessage("  Sink filling complete.")

arcpy.AddMessage("Step 2: Calculating Flow Direction...")
flow_dir = FlowDirection(filled_dem, "NORMAL")
flow_dir.save(os.path.join(WORKSPACE, "flow_dir.tif"))
arcpy.AddMessage("  Flow direction complete.")

arcpy.AddMessage("Step 3: Calculating Flow Accumulation...")
flow_acc = FlowAccumulation(flow_dir)
flow_acc.save(os.path.join(WORKSPACE, "flow_acc.tif"))
arcpy.AddMessage("  Flow accumulation complete.")

# ---- CELL 3: Stream Network Definition ----
arcpy.AddMessage("Step 4: Defining Stream Networks...")

trib_streams = Con(flow_acc > TRIB_THRESHOLD, 1)
trib_streams.save(os.path.join(WORKSPACE, "trib_streams.tif"))
arcpy.AddMessage(f"  Tributary streams defined (threshold: {TRIB_THRESHOLD})")

main_stream = Con(flow_acc > MAIN_THRESHOLD, 1)
main_stream.save(os.path.join(WORKSPACE, "main_stream.tif"))
arcpy.AddMessage(f"  Main river defined (threshold: {MAIN_THRESHOLD})")

# ---- CELL 4: HAND Calculation ----
arcpy.AddMessage("Step 5: Calculating HAND for Tributaries...")
hand_tribs = FlowDistance(trib_streams, filled_dem, flow_dir, distance_type="VERTICAL")
hand_tribs.save(os.path.join(WORKSPACE, "hand_tribs.tif"))
arcpy.AddMessage("  HAND (tributaries) complete.")

arcpy.AddMessage("Step 6: Calculating HAND for Main River...")
hand_main = FlowDistance(main_stream, filled_dem, flow_dir, distance_type="VERTICAL")
hand_main.save(os.path.join(WORKSPACE, "hand_main.tif"))
arcpy.AddMessage("  HAND (main river) complete.")

# ---- CELL 5: Flood Depth Mapping & Merge ----
arcpy.AddMessage(f"Step 7: Generating Flood Depths (Tribs: {TRIB_WATER_LEVEL}m, Main: {MAIN_WATER_LEVEL}m)...")

flood_tribs = Con(hand_tribs <= TRIB_WATER_LEVEL, TRIB_WATER_LEVEL - hand_tribs)
flood_tribs.save(os.path.join(WORKSPACE, "flood_tribs.tif"))

flood_main = Con(hand_main <= MAIN_WATER_LEVEL, MAIN_WATER_LEVEL - hand_main)
flood_main.save(os.path.join(WORKSPACE, "flood_main.tif"))

arcpy.AddMessage("Step 8: Merging Flood Maps (Maximum depth)...")
final_flood = CellStatistics([flood_tribs, flood_main], "MAXIMUM", "DATA")

arcpy.AddMessage(f"Step 9: Saving Final Flood Map to {FINAL_FLOOD_MAP}...")
final_flood.save(FINAL_FLOOD_MAP)

arcpy.AddMessage("HAND Dual-Stage Flood Mapping Complete!")

# ---- CELL 6: Add to Map Display ----
aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

if active_map:
    active_map.addDataFromPath(FINAL_FLOOD_MAP)
    active_map.addDataFromPath(os.path.join(WORKSPACE, "hand_main.tif"))
    active_map.addDataFromPath(os.path.join(WORKSPACE, "hand_tribs.tif"))
    arcpy.AddMessage("Flood map layers added to current map.")
else:
    arcpy.AddMessage("No active map found. Open a map first to auto-add layers.")

arcpy.CheckInExtension("Spatial")
