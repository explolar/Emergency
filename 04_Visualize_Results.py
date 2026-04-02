# =============================================================================
# Visualization Script for ArcGIS Pro Notebook
# Applies proper symbology to all emergency routing layers
# =============================================================================

# ---- CELL 1: Setup ----
import arcpy
import os

WORKSPACE = r"D:\Internship\hand\Hand_folde"
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")
FLOOD_MAP = os.path.join(WORKSPACE, "Beas_Final_Flood_Depth.tif")
HOSPITALS = os.path.join(WORKSPACE, "hospitals.shp")
ROADS = os.path.join(WORKSPACE, "roads.shp")

aprx = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.activeMap

if not active_map:
    print("ERROR: Open a Map view first, then re-run this cell.")
else:
    print(f"Active map: {active_map.name}")

# ---- CELL 2: Clear existing layers and add fresh ----
# Remove old layers to start clean
for lyr in active_map.listLayers():
    active_map.removeLayer(lyr)
print("Cleared existing layers.")

# Add layers in correct draw order (bottom to top)
layers_to_add = [
    FLOOD_MAP,                                              # Flood depth raster
    os.path.join(OUTPUT_GDB, "Flood_Polygon"),              # Flood extent
    ROADS,                                                  # All roads
    os.path.join(OUTPUT_GDB, "Safe_Roads"),                 # Safe roads
    os.path.join(OUTPUT_GDB, "Flooded_Roads"),              # Flooded roads
    os.path.join(OUTPUT_GDB, "Hospital_Service_Areas"),     # Service areas
    os.path.join(OUTPUT_GDB, "Emergency_Routes"),           # Routes
    HOSPITALS,                                              # Hospitals on top
]

for lyr_path in layers_to_add:
    if arcpy.Exists(lyr_path):
        active_map.addDataFromPath(lyr_path)
        print(f"  Added: {os.path.basename(lyr_path)}")
    else:
        print(f"  MISSING: {lyr_path}")

print("All layers added.")

# ---- CELL 3: Apply Symbology - Flood Depth Raster ----
for lyr in active_map.listLayers():
    if lyr.name == "Beas_Final_Flood_Depth" and lyr.isRasterLayer:
        sym = lyr.symbology

        if hasattr(sym, 'colorizer'):
            sym.updateColorizer('RasterClassifyColorizer')
            colorizer = sym.colorizer
            colorizer.classificationMethod = "NaturalBreaks"
            colorizer.breakCount = 5
            colorizer.colorRamp = aprx.listColorRamps("Blue (Continuous)")[0]
            lyr.symbology = sym
            lyr.transparency = 40
            print("Flood depth raster: Blue gradient, 40% transparent")

# ---- CELL 4: Apply Symbology - Roads & Routes ----
for lyr in active_map.listLayers():
    name = lyr.name

    if not lyr.isFeatureLayer:
        continue

    sym = lyr.symbology

    # Flooded Roads - Red thick line
    if name == "Flooded_Roads":
        sym.renderer.symbol.color = {'RGB': [255, 0, 0, 100]}
        sym.renderer.symbol.size = 3
        lyr.symbology = sym
        print("Flooded Roads: Red, 3pt")

    # Safe Roads - Green thin line
    elif name == "Safe_Roads":
        sym.renderer.symbol.color = {'RGB': [56, 168, 0, 100]}
        sym.renderer.symbol.size = 1
        lyr.symbology = sym
        print("Safe Roads: Green, 1pt")

    # All Roads - Gray background
    elif name == "roads":
        sym.renderer.symbol.color = {'RGB': [178, 178, 178, 100]}
        sym.renderer.symbol.size = 0.5
        lyr.symbology = sym
        lyr.transparency = 50
        print("All Roads: Gray, 0.5pt, 50% transparent")

    # Emergency Routes - Blue dashed thick line
    elif name == "Emergency_Routes":
        sym.renderer.symbol.color = {'RGB': [0, 92, 230, 100]}
        sym.renderer.symbol.size = 4
        lyr.symbology = sym
        print("Emergency Routes: Blue, 4pt")

    # Hospitals - Red markers
    elif name == "hospitals":
        sym.renderer.symbol.color = {'RGB': [255, 0, 0, 100]}
        sym.renderer.symbol.size = 12
        lyr.symbology = sym
        print("Hospitals: Red, 12pt")

    # Flood Polygon - Light blue fill
    elif name == "Flood_Polygon":
        sym.renderer.symbol.color = {'RGB': [0, 112, 255, 100]}
        sym.renderer.symbol.outlineColor = {'RGB': [0, 77, 168, 100]}
        lyr.symbology = sym
        lyr.transparency = 60
        print("Flood Polygon: Blue fill, 60% transparent")

    # Service Areas - graduated colors
    elif name == "Hospital_Service_Areas":
        lyr.transparency = 50
        print("Service Areas: 50% transparent")

print("\nSymbology applied!")

# ---- CELL 5: Set Map Extent to Study Area ----
# Zoom to flood extent
for lyr in active_map.listLayers():
    if lyr.name == "Beas_Final_Flood_Depth":
        ext = lyr.getExtent()
        mv = active_map.defaultView
        mv.camera.setExtent(ext)
        print("Map zoomed to study area extent.")
        break

# ---- CELL 6: Export Map Directly from Map View ----
out_png = os.path.join(WORKSPACE, "Emergency_Routing_Map.png")
out_pdf = os.path.join(WORKSPACE, "Emergency_Routing_Map.pdf")

mv = active_map.defaultView
mv.exportToPNG(out_png, width=3840, height=2160)
print(f"Exported PNG: {out_png}")

mv.exportToPDF(out_pdf, width=3840, height=2160)
print(f"Exported PDF: {out_pdf}")

print("\nTo create a layout with title & legend:")
print("  1. Insert > New Layout > A3 Landscape")
print("  2. Insert > Map Frame > drag on layout")
print("  3. Insert > Legend > click on layout")
print("  4. Insert > Text > add title")
print("  5. Share > Export Layout > PNG/PDF")

# ---- CELL 8: Add Major Places as Labels on Map ----
# Create a point shapefile with major towns/landmarks

PLACES_SHP = os.path.join(WORKSPACE, "major_places.shp")
sr = arcpy.SpatialReference(4326)

if arcpy.Exists(PLACES_SHP):
    arcpy.management.Delete(PLACES_SHP)

arcpy.management.CreateFeatureclass(
    WORKSPACE, "major_places.shp", "POINT", spatial_reference=sr
)
arcpy.management.AddField(PLACES_SHP, "name", "TEXT", field_length=100)
arcpy.management.AddField(PLACES_SHP, "place_type", "TEXT", field_length=50)

# Major places in the Beas River Basin / Kullu District
places = [
    # Towns & Cities
    {"name": "Manali",       "lon": 77.1887, "lat": 32.2396, "type": "Town"},
    {"name": "Kullu",        "lon": 77.1095, "lat": 31.9579, "type": "Town"},
    {"name": "Bhuntar",      "lon": 77.1584, "lat": 31.8776, "type": "Town"},
    {"name": "Banjar",       "lon": 77.3397, "lat": 31.6388, "type": "Town"},
    {"name": "Nagar",        "lon": 77.1300, "lat": 32.0400, "type": "Town"},
    {"name": "Mandi",        "lon": 76.9317, "lat": 31.7084, "type": "Town"},
    {"name": "Patlikuhl",    "lon": 77.1340, "lat": 32.0640, "type": "Town"},
    {"name": "Katrain",      "lon": 77.1290, "lat": 32.1000, "type": "Town"},
    {"name": "Solang",       "lon": 77.1574, "lat": 32.3150, "type": "Village"},
    {"name": "Rohtang Pass", "lon": 77.2475, "lat": 32.3722, "type": "Landmark"},
    {"name": "Manikaran",    "lon": 77.3480, "lat": 32.0275, "type": "Town"},
    {"name": "Kasol",        "lon": 77.3140, "lat": 32.0100, "type": "Town"},
    {"name": "Aut",          "lon": 77.0770, "lat": 31.8160, "type": "Town"},
    {"name": "Larji",        "lon": 77.0960, "lat": 31.7730, "type": "Village"},
    {"name": "Pandoh",       "lon": 77.0570, "lat": 31.6690, "type": "Town"},
    # Bridges (important for flood analysis)
    {"name": "Bhuntar Bridge", "lon": 77.1600, "lat": 31.8750, "type": "Bridge"},
]

with arcpy.da.InsertCursor(PLACES_SHP, ["SHAPE@", "name", "place_type"]) as cursor:
    for p in places:
        point = arcpy.PointGeometry(arcpy.Point(p["lon"], p["lat"]), sr)
        cursor.insertRow([point, p["name"], p["type"]])

print(f"Created {len(places)} major place markers.")

# Project to UTM to match other layers
PLACES_UTM = os.path.join(WORKSPACE, "major_places_utm.shp")
utm_sr = arcpy.SpatialReference(32643)
arcpy.management.Project(PLACES_SHP, PLACES_UTM, utm_sr)

# Remove duplicate place layers first
for lyr in active_map.listLayers():
    if lyr.name in ("major_places", "major_places_utm"):
        active_map.removeLayer(lyr)
print("Removed old place layers.")

# Add only the UTM version
active_map.addDataFromPath(PLACES_UTM)
print("Major places layer added to map.")

# Apply label and symbology
for lyr in active_map.listLayers():
    if lyr.name == "major_places_utm":
        # Enable labels
        lyr.showLabels = True
        lblClass = lyr.listLabelClasses()[0]
        lblClass.expression = "$feature.name"
        lblClass.visible = True

        # Make point symbols smaller (black dots)
        sym = lyr.symbology
        sym.renderer.symbol.color = {'RGB': [0, 0, 0, 100]}
        sym.renderer.symbol.size = 6
        lyr.symbology = sym
        print("Labels enabled for major places.")

print("\nMajor places: Manali, Kullu, Bhuntar, Banjar, Kasol, Manikaran, etc.")

# ---- CELL 9: Display in Notebook ----
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# Re-export with places added
out_png = os.path.join(WORKSPACE, "Emergency_Routing_Map.png")
mv = active_map.defaultView
mv.exportToPNG(out_png, width=3840, height=2160)

if os.path.exists(out_png):
    img = mpimg.imread(out_png)
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.imshow(img)
    ax.axis('off')
    ax.set_title("Emergency Routing - Beas River Basin Flood Response", fontsize=14)
    plt.tight_layout()
    plt.show()
