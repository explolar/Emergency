# Resilient Infrastructure Planning for GLOF-Prone Regions

## Technical Documentation for ArcGIS Pro Workflow

### Study Area
Beas River Basin, Kullu Valley, Himachal Pradesh, India

### Project Purpose
This project develops an ArcGIS Pro based workflow for flood inundation mapping, road vulnerability analysis, emergency routing, service area analysis, and optimal emergency center planning in a GLOF-prone Himalayan environment. The workflow is designed to support faster and safer emergency response under flood conditions by integrating terrain-derived flood depth, OpenStreetMap road infrastructure, hospital access, and network-based decision support.

---

## 1. Background and Problem Statement

Glacial Lake Outburst Floods (GLOFs), cloudburst-driven floods, and flood-related landslides are increasing the risk to settlements and infrastructure in the Western Himalayas. In the Kullu Valley, emergency response is particularly difficult because:

- roads can become flooded or impassable very quickly,
- mountainous terrain reduces route alternatives,
- emergency facilities are unevenly distributed,
- flooded road segments affect both travel time and vehicle stability,
- conventional flood maps often show only inundation extent and do not directly support mobility planning.

The ArcGIS workflow developed in this project addresses that gap by moving from flood mapping to operational emergency planning.

---

## 2. Project Objectives

### Objective 1. Flood Risk Zone Classification
Generate local flood inundation outputs and classify areas into flood risk zones from high risk to low risk.

### Objective 2. Road Vulnerability and Vehicular Mobility Assessment
Identify which road segments remain usable under flood conditions, estimate safe speed, and determine safe evacuation routes for emergency vehicles.

### Objective 3. Optimal Emergency Service Location
Identify candidate and optimal locations for emergency response centers so that flood-affected demand points can be reached within the target response time.

---

## 3. Software Environment

### Software
- ArcGIS Pro Notebook environment
- Python with `arcpy`
- Spatial Analyst extension
- Network Analyst extension
- `matplotlib` for chart generation

### ArcGIS Dependencies
The workflow depends on:

- `arcpy.sa` for raster and hydrologic analysis,
- `arcpy.na` for network analysis,
- `arcpy.mp.ArcGISProject("CURRENT")` for map automation and visualization.

Because of this, the scripts are intended to be run inside ArcGIS Pro and not as standalone Python scripts in a normal terminal.

---

## 4. Script Inventory and Execution Order

The project consists of five main scripts:

1. `01_HAND_Flood_Mapping.py`
2. `02_Download_Data.py`
3. `03_Emergency_Routing.py`
4. `04_Visualize_Results.py`
5. `05_Generate_Graphs.py`

### Required Execution Order

1. Run `01_HAND_Flood_Mapping.py`
2. Run `02_Download_Data.py`
3. Run `03_Emergency_Routing.py`
4. Optionally run `04_Visualize_Results.py` for map styling and export
5. Run `05_Generate_Graphs.py` for statistical graphs

The first three scripts are the core analytical pipeline. The last two are presentation and reporting layers built on the outputs of the core analysis.

---

## 5. Folder Structure and Main Paths

### Working Folder
`D:\Internship\hand\Hand_folde`

### Graph Output Folder
`D:\Internship\hand\graph`

### Important Inputs
- DEM: `Bease_River_Basin_DEM-002.tif`
- Roads: created from OpenStreetMap
- Hospitals: created from OpenStreetMap plus fallback known facilities

### Main Output Geodatabase
`Emergency_Routing.gdb`

---

## 6. Data Inputs

### 6.1 Digital Elevation Model
The DEM is the foundational terrain input for the flood workflow. It is used for:

- sink filling,
- flow direction and flow accumulation,
- stream extraction,
- HAND calculation,
- elevation sampling at road vertices.

### 6.2 Road Network
Roads are downloaded from OpenStreetMap using Overpass API and converted into ArcGIS polyline feature classes. The script includes important highway classes such as:

- motorway,
- trunk,
- primary,
- secondary,
- tertiary,
- residential,
- unclassified,
- service,
- track.

### 6.3 Hospitals and Healthcare Facilities
Healthcare facilities are extracted from OpenStreetMap using tags such as:

- `amenity=hospital`
- `amenity=clinic`
- `amenity=doctors`
- `healthcare=hospital`
- `healthcare=clinic`
- `building=hospital`

If OSM does not return all facilities, fallback known hospitals are inserted manually.

---

## 7. Methodology Overview

The workflow can be understood as five major technical stages:

1. Terrain-based flood depth estimation using HAND
2. Download and preparation of roads and hospitals
3. Road vulnerability and emergency routing analysis
4. Visualization and map export
5. Graph generation and reporting

---

## 8. Detailed Technical Procedure

## 8.1 Stage 1: HAND-Based Flood Mapping

### Script
`01_HAND_Flood_Mapping.py`

### Purpose
Generate a final flood depth raster using a dual-stage HAND approach that distinguishes tributary flooding and main-river flooding.

### 8.1.1 Setup
The script sets:

- ArcGIS workspace,
- output compression,
- overwrite rules,
- parallel processing factor,
- input DEM path,
- output flood raster path.

### 8.1.2 Hydrologic Preprocessing
The following raster operations are applied:

1. `Fill`
   Removes local depressions and sink artifacts from the DEM.

2. `FlowDirection`
   Derives direction of steepest descent for each raster cell.

3. `FlowAccumulation`
   Computes upstream contributing area, allowing stream network extraction.

### 8.1.3 Stream Network Definition
Two stream systems are generated using different accumulation thresholds:

- Tributary threshold: `160000`
- Main river threshold: `1500000`

This allows the analysis to model smaller tributaries and the main Beas River separately rather than applying one water level everywhere.

### 8.1.4 HAND Calculation
HAND represents height above nearest drainage and is computed using:

- `FlowDistance(..., distance_type="VERTICAL")`

Two HAND surfaces are created:

- `hand_tribs.tif`
- `hand_main.tif`

### 8.1.5 Flood Depth Generation
Flood depth is estimated by comparing HAND values to assumed water levels:

- Tributary water level: `5.0 m`
- Main river water level: `12.0 m`

For each raster:

`Flood Depth = Water Level - HAND`, where HAND is less than or equal to the assumed water level.

Two flood rasters are generated:

- `flood_tribs.tif`
- `flood_main.tif`

### 8.1.6 Merging Flood Rasters
The final flood depth surface is created using:

- `CellStatistics(..., "MAXIMUM", "DATA")`

This preserves the maximum flood depth at each pixel from either tributary or main-river influence.

### 8.1.7 Main Outputs
- `filled_dem.tif`
- `flow_dir.tif`
- `flow_acc.tif`
- `trib_streams.tif`
- `main_stream.tif`
- `hand_tribs.tif`
- `hand_main.tif`
- `flood_tribs.tif`
- `flood_main.tif`
- `Beas_Final_Flood_Depth.tif`

---

## 8.2 Stage 2: Downloading and Preparing Roads and Hospitals

### Script
`02_Download_Data.py`

### Purpose
Extract study-area roads and healthcare facilities from OpenStreetMap and prepare them in ArcGIS-ready format.

### 8.2.1 Extent Extraction
The DEM extent is read using `arcpy.Describe`. If the DEM is projected, the script reprojects its corner coordinates to WGS84 so that OpenStreetMap can be queried using latitude and longitude.

### 8.2.2 Road Download
Roads are downloaded from Overpass API. To reduce timeout risk, the bounding box is divided into four quadrants:

- southwest,
- southeast,
- northwest,
- northeast.

For each chunk:

- a road query is submitted,
- failed requests are retried up to 3 times,
- a delay is inserted between requests to respect rate limits,
- duplicate ways are removed after merge.

### 8.2.3 Road Feature Class Construction
The script creates a road shapefile with fields such as:

- `osm_id`
- `highway`
- `name`
- `maxspeed`
- `oneway`
- `surface`

### 8.2.4 Travel Time Fields
The following additional fields are calculated:

- `length_km`
- `travel_min`

If `maxspeed` is missing in OSM, the script uses default speeds by road type. Travel time is then derived as:

`Travel Time (min) = (Length_km / Speed_kmh) * 60`

### 8.2.5 Hospital Download
Hospitals and clinics are downloaded from OSM using point and area queries. If OSM is incomplete, known district hospitals are inserted manually.

### 8.2.6 Projection to UTM
Both roads and hospitals are projected to:

- `UTM Zone 43N`
- EPSG: `32643`

### 8.2.7 Main Outputs
- `roads_wgs84.shp`
- `hospitals_wgs84.shp`
- `roads.shp`
- `hospitals.shp`

---

## 8.3 Stage 3: Emergency Routing and Vulnerability Analysis

### Script
`03_Emergency_Routing.py`

### Purpose
Perform flood risk classification, road vulnerability analysis, safe speed estimation, emergency route generation, service area analysis, and optimal center allocation.

### 8.3.1 Workspace Cleanup
The script begins by:

- checking in any held extensions,
- clearing all layers from the active ArcGIS map,
- clearing in-memory workspace,
- deleting any previous output geodatabase,
- recreating `Emergency_Routing.gdb`,
- deleting stale rasters.

This ensures clean and repeatable analysis.

### 8.3.2 Creating a Float Flood Depth Surface
Because DEM-derived rasters can remain integer typed, the script resamples the HAND rasters using a shrink-expand bilinear method to force floating-point interpolation.

This is done so that flood depth is not limited to coarse integer increments.

Generated rasters include:

- `hand_tribs_float.tif`
- `hand_main_float.tif`
- `flood_depth_float.tif`

### 8.3.3 Flood Risk Classification
Flood depth is grouped into four classes:

- `3 = Red / Major` for depth greater than `1.5 m`
- `2 = Orange / Moderate` for depth between `0.5 m` and `1.5 m`
- `1 = Yellow / Minor` for depth between `0 m` and `0.5 m`
- `0 = Green / No Flood` for `0 m`

The raster is converted to polygons and labeled with:

- `risk_level`
- `depth_range`

### 8.3.4 Safe Speed Mapping Using Pregnolato Function
The script uses the depth-disruption function:

`v(w) = 0.0009w^2 - 0.5529w + 86.9448`

where:

- `w` is water depth in millimeters,
- `v` is safe speed in km/h.

In meters this becomes:

`v = 900d^2 - 552.9d + 86.9448`

where `d` is water depth in meters.

Additional rules applied in the script:

- depth less than or equal to `0` -> `86.94 km/h`
- depth greater than `0.30 m` -> `0 km/h`
- values are clamped to the range `0` to `86.94 km/h`

The resulting speed raster is classified into:

- `60-87 km/h`
- `40-60 km/h`
- `20-40 km/h`
- `10-20 km/h`
- `0-10 km/h`
- `0 km/h`

### 8.3.5 Road Vulnerability Assessment
The roads are projected dynamically to match the DEM coordinate system. Then:

1. road attributes are extended with flood and mobility fields,
2. vertices are densified every `1 meter`,
3. vertices are converted to points,
4. DEM elevation is sampled at each vertex,
5. flood depth is sampled at each vertex,
6. statistics are aggregated back to each road segment.

Added road fields include:

- `flood_depth`
- `avg_depth`
- `min_elev`
- `max_elev`
- `safe_speed`
- `small_car`
- `ambulance`
- `heavy_veh`
- `road_status`

### 8.3.6 Vehicle Stability Thresholds
The script uses conservative Himalayan thresholds:

- Small car: `0.25 m`
- Ambulance / SUV: `0.35 m`
- Heavy / Fire vehicle: `0.45 m`

Additional threshold:

- Minimum instability depth: `0.20 m`

Road status is classified as:

- `Safe` for depth equal to `0`
- `Caution` for depth less than `0.20 m`
- `Restricted` for depth between `0.20 m` and `0.45 m`
- `Impassable` for depth greater than or equal to `0.45 m`

### 8.3.7 Road Subsets
Separate feature classes are created:

- `Traversable_Roads`
- `Blocked_Roads`
- `Restricted_Roads`
- `Emergency_Vehicle_Roads`

Emergency vehicles are allowed to use all roads except those marked `Impassable`.

### 8.3.8 Flood-Adjusted Travel Time
Travel time on the emergency road network is recalculated using the flood-adjusted safe speed:

`Flood Time (min) = (Length_km / Safe_Speed_kmh) * 60`

The resulting field is:

- `flood_time`

### 8.3.9 Network Dataset Creation
The emergency roads are copied into a feature dataset and a network dataset is built using ArcGIS Network Analyst.

This supports:

- closest facility analysis,
- service area analysis,
- location-allocation analysis.

### 8.3.10 Closest Facility Analysis
Flood extent polygons are derived from the flood raster. Large polygons only are retained:

- area greater than `10,000 sq m`

Centroids of these polygons become emergency demand points or incident points.

Hospitals are loaded as facilities, and ArcGIS computes the closest available routes under the time cutoff:

- response time target: `20 minutes`

Output:

- `Emergency_Routes`

### 8.3.11 Service Area Analysis
Service areas are generated from hospital locations using these cutoffs:

- `5 minutes`
- `10 minutes`
- `15 minutes`
- `20 minutes`

Output:

- `Hospital_Service_Areas`

This shows how much area can be covered by current facilities under flood-adjusted travel conditions.

### 8.3.12 Location-Allocation Analysis
Candidate emergency center points are generated every:

- `2000 meters`

along traversable roads.

Location-allocation is solved with:

- problem type: `MINIMIZE_IMPEDANCE`
- cutoff: `20 minutes`
- existing hospitals loaded as required facilities
- candidate points loaded as optional facilities
- flood-centroid demand points loaded as demand

Outputs:

- `Candidate_Locations`
- `Optimal_Emergency_Centers`
- `Allocation_Lines`

---

## 8.4 Stage 4: Visualization and Map Export

### Script
`04_Visualize_Results.py`

### Purpose
Load outputs into ArcGIS Pro, apply symbology, export map products, and add key place labels.

### Visualization Tasks
- clears the active map,
- adds raster and vector outputs in display order,
- styles flooded roads, safe roads, routes, hospitals, service areas, and flood polygons,
- zooms to study extent,
- exports PNG and PDF maps,
- creates and adds a labeled major places layer.

This stage is primarily cartographic and presentation-oriented.

---

## 8.5 Stage 5: Graph Generation and Reporting

### Script
`05_Generate_Graphs.py`

### Purpose
Generate analytical charts from the geodatabase outputs and save them to:

`D:\Internship\hand\graph`

### Graphs Generated

1. `01_flood_risk_distribution.png`
   Flood risk by polygon count and flood risk by area

2. `02_road_status_distribution.png`
   Road status by segment count and road length

3. `03_vehicle_passability.png`
   Passable versus impassable road segments for:
   - small car
   - ambulance / SUV
   - heavy / fire truck

4. `04_flood_depth_distribution.png`
   Distribution of road segments by flood-depth range

5. `05_safe_speed_distribution.png`
   Safe speed distribution by count and total road length

6. `06_service_area_coverage.png`
   Area covered within each response-time band

7. `07_emergency_route_distribution.png`
   Distribution of route travel time and route length

8. `08_optimal_center_summary.png`
   Existing versus new optimal centers and candidate-versus-selected comparison

9. `09_depth_vs_safe_speed.png`
   Scatter plot showing the relationship between flood depth and safe speed

10. `10_summary_dashboard.png`
    Multi-panel dashboard summarizing key project outcomes

### Graph Logic
The graph script reads directly from:

- `Flood_Risk_Zones`
- `Road_Vulnerability`
- `Hospital_Service_Areas`
- `Emergency_Routes`
- `Optimal_Emergency_Centers`
- `Candidate_Locations`

The script is written defensively. If any layer is missing, it skips only the relevant graph and continues.

---

## 9. Interpretation of Key Metrics

## 9.1 Flood Risk
The flood-risk outputs communicate the severity of inundation spatially. The key interpretation is:

- Red zones indicate severe flooding and possible life-threatening conditions,
- Orange zones indicate moderate flood impact and damage potential,
- Yellow zones indicate shallow flooding that can still disrupt road access,
- Green zones indicate no modeled flood water.

## 9.2 Road Status
Road status is the main mobility output:

- `Safe` roads are usable without flood impact,
- `Caution` roads remain passable but require reduced speed and high care,
- `Restricted` roads are risky and only suitable for stronger vehicles,
- `Impassable` roads should be excluded from emergency routing.

## 9.3 Safe Speed
Safe speed is not the legal speed limit. It is the flood-adjusted maximum operational speed estimated from water depth using the depth-disruption function. This is highly useful for emergency planning because it converts flood conditions into a travel-time penalty on the road network.

## 9.4 Vehicle Passability
The vehicle passability charts show how many roads remain usable for different emergency vehicle categories. This is important because an ambulance, small car, and heavy rescue vehicle do not share the same flood tolerance.

## 9.5 Service Areas
Service area outputs show which flooded regions can be reached within the operational target of 20 minutes. Gaps in coverage indicate where new service centers or shelters may be needed.

## 9.6 Location-Allocation
Location-allocation provides a more strategic output than routing. Routing answers:

"How do we get there now?"

Location-allocation answers:

"Where should we place resources so that future response is faster and more equitable?"

---

## 10. Detailed Run Procedure in ArcGIS Pro

### Step 1. Open ArcGIS Pro
- open the project,
- open a map view,
- open Notebook.

### Step 2. Verify Extensions
Make sure:

- Spatial Analyst is available,
- Network Analyst is available.

### Step 3. Verify Paths
Confirm that the hard-coded paths in the scripts match your machine:

- `D:\Internship\hand\Hand_folde`
- `D:\Internship\hand\Bease_River_Basin_DEM-002.tif`
- `D:\Internship\hand\graph`

### Step 4. Run `01_HAND_Flood_Mapping.py`
Expected result:

- final flood raster generated,
- HAND rasters created,
- flood depth outputs added to map.

### Step 5. Run `02_Download_Data.py`
Expected result:

- roads downloaded and saved,
- hospitals downloaded and supplemented,
- both projected to UTM 43N.

### Step 6. Run `03_Emergency_Routing.py`
Expected result:

- output geodatabase created,
- risk zones generated,
- safe speed raster produced,
- roads classified,
- routes solved,
- service areas created,
- optimal center selection completed.

### Step 7. Run `04_Visualize_Results.py`
Expected result:

- clean thematic map,
- exported PNG and PDF,
- labeled towns and landmarks.

### Step 8. Run `05_Generate_Graphs.py`
Expected result:

- chart PNGs written to `D:\Internship\hand\graph`

---

## 11. Output Inventory

### Raster Outputs
- flood depth raster
- HAND rasters
- flood risk raster
- safe speed raster
- safe speed class raster

### Feature Outputs
- flood risk polygons
- road vulnerability layer
- traversable roads
- restricted roads
- blocked roads
- emergency routes
- service areas
- candidate locations
- optimal emergency centers
- allocation lines

### Presentation Outputs
- map PNG and PDF
- graph PNGs

---

## 12. Technical Strengths of the Workflow

- integrates raster hydrology with network analysis,
- converts flood depth into mobility and routing consequences,
- incorporates vehicle-specific operational thresholds,
- produces both tactical outputs and strategic planning outputs,
- supports direct ArcGIS map and graph export,
- is modular and can be rerun with updated DEM, roads, or facilities.

---

## 13. Technical Limitations

Although the workflow is operationally useful, the following limitations should be acknowledged:

- flood depth is generated from a HAND-based surrogate approach rather than a full dynamic hydraulic model in the current implementation,
- flood velocity is referenced in the methodology but is not explicitly modeled in the implemented scripts,
- safe speed is derived from a published empirical relation and not from local vehicle experiments,
- OSM road completeness and hospital completeness can vary,
- location-allocation depends on the quality of candidate generation and demand-point representation,
- route solving assumes the postprocessed road network is topologically suitable for Network Analyst.

---

## 14. Recommended Future Improvements

- integrate true MIKE+ flood outputs for depth, extent, and velocity,
- incorporate bridge vulnerability and landslide blockage layers,
- include population-at-risk and vulnerable-group weighting in demand points,
- validate safe speed thresholds with local responder vehicle types,
- incorporate dynamic rainfall scenarios and seasonal variability,
- automate summary table export to CSV or Excel,
- create layout templates for publication-quality map output.

---

## 15. Suggested Reporting Language

The workflow can be described in technical reporting as follows:

"A GIS-based decision-support workflow was developed in ArcGIS Pro for flood-risk classification, road vulnerability assessment, emergency route optimization, and emergency facility location planning in the Beas River Basin. Terrain-derived flood depth was integrated with road-network accessibility to estimate flood-adjusted safe speeds, classify passability for different emergency vehicle categories, compute quickest evacuation routes, delineate service areas, and identify optimal locations for emergency response centers under a 20-minute response threshold."

---

## 16. Conclusion

This ArcGIS Pro workflow forms a complete technical chain from terrain-derived flood mapping to practical emergency response planning. It does not stop at identifying where flooding occurs; it extends the analysis to determine:

- which roads remain usable,
- how quickly emergency vehicles can move,
- which flood-affected zones are reachable in time,
- where new response facilities should ideally be placed.

For a Himalayan study area such as Kullu Valley, this makes the workflow operationally meaningful for disaster preparedness, rescue planning, and infrastructure resilience assessment.

---

## 17. How This Document Should Be Used

This file can be used as:

- technical project documentation,
- a report appendix,
- methodology documentation for a thesis or internship submission,
- speaking notes for a technical presentation,
- a base document for preparing a formal Word or PDF report.
