"""
Generate presentation-ready graphs from the ArcGIS emergency-routing outputs.

Run this after:
1. 01_HAND_Flood_Mapping.py
2. 02_Download_Data.py
3. 03_Emergency_Routing.py

All charts are saved to:
    D:\\Internship\\hand\\graph
"""

import os
from collections import OrderedDict

import arcpy
import matplotlib.pyplot as plt


WORKSPACE = r"D:\Internship\hand\Hand_folde"
OUTPUT_GDB = os.path.join(WORKSPACE, "Emergency_Routing.gdb")
GRAPH_DIR = r"D:\Internship\hand\graph"

FLOOD_RISK_ZONES = os.path.join(OUTPUT_GDB, "Flood_Risk_Zones")
ROAD_VULNERABILITY = os.path.join(OUTPUT_GDB, "Road_Vulnerability")
SERVICE_AREAS = os.path.join(OUTPUT_GDB, "Hospital_Service_Areas")
EMERGENCY_ROUTES = os.path.join(OUTPUT_GDB, "Emergency_Routes")
OPTIMAL_CENTERS = os.path.join(OUTPUT_GDB, "Optimal_Emergency_Centers")
CANDIDATE_LOCATIONS = os.path.join(OUTPUT_GDB, "Candidate_Locations")
HOSPITALS = os.path.join(WORKSPACE, "hospitals.shp")


plt.style.use("seaborn-v0_8-whitegrid")

os.makedirs(GRAPH_DIR, exist_ok=True)
saved_graphs = []


def save_figure(fig, filename):
    out_path = os.path.join(GRAPH_DIR, filename)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    saved_graphs.append(out_path)
    print(f"Saved graph: {out_path}")


def label_bars(ax, bars, fmt="{:.0f}", offset=0.01):
    ymax = ax.get_ylim()[1]
    lift = ymax * offset if ymax else 0.1
    for bar in bars:
        value = bar.get_height()
        ax.text(
            bar.get_x() + (bar.get_width() / 2.0),
            value + lift,
            fmt.format(value),
            ha="center",
            va="bottom",
            fontsize=9,
        )


def numeric_fields(feature_class):
    numeric_types = {"SmallInteger", "Integer", "Single", "Double"}
    return [f.name for f in arcpy.ListFields(feature_class) if f.type in numeric_types]


def find_field(feature_class, preferred_tokens):
    candidates = numeric_fields(feature_class)
    lowered = {field.lower(): field for field in candidates}

    for token in preferred_tokens:
        token = token.lower()
        for lower_name, original_name in lowered.items():
            if token == lower_name:
                return original_name
        for lower_name, original_name in lowered.items():
            if token in lower_name:
                return original_name
    return None


def percent(value, total):
    return (value / total * 100.0) if total else 0.0


def classify_depth(depth_m):
    if depth_m is None or depth_m <= 0:
        return "0 m"
    if depth_m < 0.2:
        return "0-0.2 m"
    if depth_m < 0.5:
        return "0.2-0.5 m"
    if depth_m < 1.5:
        return "0.5-1.5 m"
    return ">1.5 m"


def classify_speed(speed_kmh):
    if speed_kmh is None or speed_kmh <= 0:
        return "0 km/h"
    if speed_kmh < 10:
        return "0-10 km/h"
    if speed_kmh < 20:
        return "10-20 km/h"
    if speed_kmh < 40:
        return "20-40 km/h"
    if speed_kmh < 60:
        return "40-60 km/h"
    return "60-87 km/h"


print("=" * 70)
print("GENERATING ANALYSIS GRAPHS")
print("=" * 70)
print(f"Graph output folder: {GRAPH_DIR}")


# ---------------------------------------------------------------------------
# 1. Flood risk zone distribution
# ---------------------------------------------------------------------------
if arcpy.Exists(FLOOD_RISK_ZONES):
    zone_labels = OrderedDict([
        (3, "Red - Major"),
        (2, "Orange - Moderate"),
        (1, "Yellow - Minor"),
        (0, "Green - No Flood"),
    ])
    zone_colors = {
        3: "#c1121f",
        2: "#f77f00",
        1: "#fcbf49",
        0: "#2a9d8f",
    }
    zone_counts = {key: 0 for key in zone_labels}
    zone_areas_km2 = {key: 0.0 for key in zone_labels}

    with arcpy.da.SearchCursor(FLOOD_RISK_ZONES, ["gridcode", "SHAPE@AREA"]) as cursor:
        for gridcode, area_m2 in cursor:
            if gridcode in zone_counts:
                zone_counts[gridcode] += 1
                zone_areas_km2[gridcode] += area_m2 / 1e6

    labels = [zone_labels[key] for key in zone_labels]
    counts = [zone_counts[key] for key in zone_labels]
    areas = [zone_areas_km2[key] for key in zone_labels]
    colors = [zone_colors[key] for key in zone_labels]

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    bars1 = axes[0].bar(labels, counts, color=colors, edgecolor="black")
    axes[0].set_title("Flood Risk Distribution by Polygon Count", fontsize=12, weight="bold")
    axes[0].set_ylabel("Polygon Count")
    axes[0].tick_params(axis="x", rotation=20)
    label_bars(axes[0], bars1, "{:.0f}")

    bars2 = axes[1].bar(labels, areas, color=colors, edgecolor="black")
    axes[1].set_title("Flood Risk Distribution by Area", fontsize=12, weight="bold")
    axes[1].set_ylabel("Area (sq km)")
    axes[1].tick_params(axis="x", rotation=20)
    label_bars(axes[1], bars2, "{:.2f}")

    plt.suptitle("Objective 1: Flood Risk Zone Distribution", fontsize=14, weight="bold")
    plt.tight_layout()
    save_figure(fig, "01_flood_risk_distribution.png")
else:
    print("Skipped flood risk graphs: Flood_Risk_Zones not found.")


# ---------------------------------------------------------------------------
# Read road vulnerability once and reuse the values for multiple graphs
# ---------------------------------------------------------------------------
road_rows = []
if arcpy.Exists(ROAD_VULNERABILITY):
    with arcpy.da.SearchCursor(
        ROAD_VULNERABILITY,
        ["road_status", "flood_depth", "safe_speed", "small_car", "ambulance", "heavy_veh", "SHAPE@LENGTH"],
    ) as cursor:
        for row in cursor:
            road_rows.append(row)
else:
    print("Skipped road-based graphs: Road_Vulnerability not found.")


# ---------------------------------------------------------------------------
# 2. Road status distribution
# ---------------------------------------------------------------------------
if road_rows:
    status_order = ["Safe", "Caution", "Restricted", "Impassable"]
    status_colors = {
        "Safe": "#2a9d8f",
        "Caution": "#f4d35e",
        "Restricted": "#f4a261",
        "Impassable": "#c1121f",
    }
    status_counts = {status: 0 for status in status_order}
    status_lengths = {status: 0.0 for status in status_order}

    for status, _depth, _speed, _small, _amb, _heavy, length_m in road_rows:
        if status in status_counts:
            status_counts[status] += 1
            status_lengths[status] += (length_m or 0.0) / 1000.0

    labels = status_order
    counts = [status_counts[label] for label in labels]
    lengths = [status_lengths[label] for label in labels]
    colors = [status_colors[label] for label in labels]

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    bars1 = axes[0].bar(labels, counts, color=colors, edgecolor="black")
    axes[0].set_title("Road Status by Segment Count", fontsize=12, weight="bold")
    axes[0].set_ylabel("Number of Segments")
    label_bars(axes[0], bars1, "{:.0f}")

    bars2 = axes[1].bar(labels, lengths, color=colors, edgecolor="black")
    axes[1].set_title("Road Status by Length", fontsize=12, weight="bold")
    axes[1].set_ylabel("Road Length (km)")
    label_bars(axes[1], bars2, "{:.2f}")

    plt.suptitle("Objective 2: Road Status Distribution", fontsize=14, weight="bold")
    plt.tight_layout()
    save_figure(fig, "02_road_status_distribution.png")


# ---------------------------------------------------------------------------
# 3. Vehicle passability comparison
# ---------------------------------------------------------------------------
if road_rows:
    vehicle_specs = [
        ("small_car", "Small Car"),
        ("ambulance", "Ambulance / SUV"),
        ("heavy_veh", "Heavy / Fire Truck"),
    ]
    passable = []
    impassable = []

    for field_name, _label in vehicle_specs:
        field_index = {
            "small_car": 3,
            "ambulance": 4,
            "heavy_veh": 5,
        }[field_name]
        p_count = 0
        i_count = 0
        for row in road_rows:
            value = row[field_index]
            if value == "Passable":
                p_count += 1
            else:
                i_count += 1
        passable.append(p_count)
        impassable.append(i_count)

    labels = [label for _field_name, label in vehicle_specs]
    x = range(len(labels))

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x, passable, width=0.6, label="Passable", color="#2a9d8f", edgecolor="black")
    bars2 = ax.bar(
        x,
        impassable,
        width=0.6,
        bottom=passable,
        label="Impassable",
        color="#c1121f",
        edgecolor="black",
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Number of Road Segments")
    ax.set_title("Vehicle Passability by Vehicle Type", fontsize=13, weight="bold")
    ax.legend()

    for bars in (bars1, bars2):
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(
                    bar.get_x() + (bar.get_width() / 2.0),
                    bar.get_y() + (height / 2.0),
                    f"{int(height)}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="white" if bar.get_facecolor()[0] < 0.7 else "black",
                    weight="bold",
                )

    plt.tight_layout()
    save_figure(fig, "03_vehicle_passability.png")


# ---------------------------------------------------------------------------
# 4. Flood depth distribution on roads
# ---------------------------------------------------------------------------
if road_rows:
    depth_order = ["0 m", "0-0.2 m", "0.2-0.5 m", "0.5-1.5 m", ">1.5 m"]
    depth_counts = {label: 0 for label in depth_order}
    depth_lengths = {label: 0.0 for label in depth_order}
    depth_colors = {
        "0 m": "#2a9d8f",
        "0-0.2 m": "#8ecae6",
        "0.2-0.5 m": "#ffd166",
        "0.5-1.5 m": "#f4a261",
        ">1.5 m": "#c1121f",
    }

    for _status, depth, _speed, _small, _amb, _heavy, length_m in road_rows:
        label = classify_depth(depth)
        depth_counts[label] += 1
        depth_lengths[label] += (length_m or 0.0) / 1000.0

    labels = depth_order
    counts = [depth_counts[label] for label in labels]
    lengths = [depth_lengths[label] for label in labels]
    colors = [depth_colors[label] for label in labels]

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    bars1 = axes[0].bar(labels, counts, color=colors, edgecolor="black")
    axes[0].set_title("Flood Depth on Roads by Segment Count", fontsize=12, weight="bold")
    axes[0].set_ylabel("Number of Segments")
    axes[0].tick_params(axis="x", rotation=15)
    label_bars(axes[0], bars1, "{:.0f}")

    bars2 = axes[1].bar(labels, lengths, color=colors, edgecolor="black")
    axes[1].set_title("Flood Depth on Roads by Length", fontsize=12, weight="bold")
    axes[1].set_ylabel("Road Length (km)")
    axes[1].tick_params(axis="x", rotation=15)
    label_bars(axes[1], bars2, "{:.2f}")

    plt.suptitle("Road Flood Depth Distribution", fontsize=14, weight="bold")
    plt.tight_layout()
    save_figure(fig, "04_flood_depth_distribution.png")


# ---------------------------------------------------------------------------
# 5. Safe speed distribution
# ---------------------------------------------------------------------------
if road_rows:
    speed_order = ["60-87 km/h", "40-60 km/h", "20-40 km/h", "10-20 km/h", "0-10 km/h", "0 km/h"]
    speed_counts = {label: 0 for label in speed_order}
    speed_lengths = {label: 0.0 for label in speed_order}
    speed_colors = {
        "60-87 km/h": "#2a9d8f",
        "40-60 km/h": "#52b788",
        "20-40 km/h": "#ffd166",
        "10-20 km/h": "#f4a261",
        "0-10 km/h": "#e76f51",
        "0 km/h": "#c1121f",
    }

    for _status, _depth, safe_speed, _small, _amb, _heavy, length_m in road_rows:
        label = classify_speed(safe_speed)
        speed_counts[label] += 1
        speed_lengths[label] += (length_m or 0.0) / 1000.0

    labels = speed_order
    counts = [speed_counts[label] for label in labels]
    lengths = [speed_lengths[label] for label in labels]
    colors = [speed_colors[label] for label in labels]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    bars1 = axes[0].bar(labels, counts, color=colors, edgecolor="black")
    axes[0].set_title("Road Safe Speed Distribution by Segment Count", fontsize=12, weight="bold")
    axes[0].set_ylabel("Number of Segments")
    axes[0].tick_params(axis="x", rotation=20)
    label_bars(axes[0], bars1, "{:.0f}")

    bars2 = axes[1].bar(labels, lengths, color=colors, edgecolor="black")
    axes[1].set_title("Road Safe Speed Distribution by Length", fontsize=12, weight="bold")
    axes[1].set_ylabel("Road Length (km)")
    axes[1].tick_params(axis="x", rotation=20)
    label_bars(axes[1], bars2, "{:.2f}")

    plt.suptitle("Safe Driving Speed Distribution", fontsize=14, weight="bold")
    plt.tight_layout()
    save_figure(fig, "05_safe_speed_distribution.png")


# ---------------------------------------------------------------------------
# 6. Service area coverage by response time
# ---------------------------------------------------------------------------
if arcpy.Exists(SERVICE_AREAS):
    to_break_field = find_field(SERVICE_AREAS, ["tobreak", "to_break"])
    from_break_field = find_field(SERVICE_AREAS, ["frombreak", "from_break"])

    if to_break_field:
        coverage = {}
        fields = [to_break_field, "SHAPE@AREA"]
        if from_break_field:
            fields.insert(0, from_break_field)

        with arcpy.da.SearchCursor(SERVICE_AREAS, fields) as cursor:
            for row in cursor:
                if from_break_field:
                    from_break, to_break, area_m2 = row
                    label = f"{int(from_break)}-{int(to_break)} min"
                else:
                    to_break, area_m2 = row
                    label = f"0-{int(to_break)} min"
                coverage[label] = coverage.get(label, 0.0) + (area_m2 / 1e6)

        ordered_labels = sorted(
            coverage.keys(),
            key=lambda item: int(item.split("-")[0]),
        )
        ordered_areas = [coverage[label] for label in ordered_labels]

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(ordered_labels, ordered_areas, color="#3a86ff", edgecolor="black")
        ax.set_title("Hospital Service Area Coverage by Response Time", fontsize=13, weight="bold")
        ax.set_xlabel("Response Time Class")
        ax.set_ylabel("Area Covered (sq km)")
        label_bars(ax, bars, "{:.2f}")
        plt.tight_layout()
        save_figure(fig, "06_service_area_coverage.png")
    else:
        print("Skipped service area graph: break fields not found in Hospital_Service_Areas.")
else:
    print("Skipped service area graph: Hospital_Service_Areas not found.")


# ---------------------------------------------------------------------------
# 7. Emergency routes travel-time and length graph
# ---------------------------------------------------------------------------
if arcpy.Exists(EMERGENCY_ROUTES):
    time_field = find_field(
        EMERGENCY_ROUTES,
        ["total_minutes", "minutes", "traveltime", "travel_time", "totaltime", "time"],
    )
    length_field = find_field(
        EMERGENCY_ROUTES,
        ["total_kilometers", "total_length", "totallength", "shape_length", "length"],
    )

    route_times = []
    route_lengths_km = []

    fields = []
    if time_field:
        fields.append(time_field)
    if length_field and length_field not in fields:
        fields.append(length_field)

    if fields:
        with arcpy.da.SearchCursor(EMERGENCY_ROUTES, fields) as cursor:
            for row in cursor:
                idx = 0
                time_value = None
                length_value = None

                if time_field:
                    time_value = row[idx]
                    idx += 1
                if length_field:
                    length_value = row[idx]

                if time_value is not None:
                    route_times.append(float(time_value))
                if length_value is not None:
                    route_lengths_km.append(float(length_value) / 1000.0 if "shape" in length_field.lower() else float(length_value))

    if not route_lengths_km:
        with arcpy.da.SearchCursor(EMERGENCY_ROUTES, ["SHAPE@LENGTH"]) as cursor:
            for (length_m,) in cursor:
                route_lengths_km.append((length_m or 0.0) / 1000.0)

    if route_times or route_lengths_km:
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))

        if route_times:
            axes[0].hist(route_times, bins=10, color="#8338ec", edgecolor="black")
            axes[0].set_title("Emergency Route Travel Time Distribution", fontsize=12, weight="bold")
            axes[0].set_xlabel("Travel Time (minutes)")
            axes[0].set_ylabel("Route Count")
        else:
            axes[0].text(0.5, 0.5, "No route-time field found", ha="center", va="center", fontsize=12)
            axes[0].set_axis_off()

        axes[1].hist(route_lengths_km, bins=10, color="#118ab2", edgecolor="black")
        axes[1].set_title("Emergency Route Length Distribution", fontsize=12, weight="bold")
        axes[1].set_xlabel("Route Length (km)")
        axes[1].set_ylabel("Route Count")

        plt.suptitle("Emergency Route Distributions", fontsize=14, weight="bold")
        plt.tight_layout()
        save_figure(fig, "07_emergency_route_distribution.png")
    else:
        print("Skipped emergency route graph: no route values found.")
else:
    print("Skipped emergency route graph: Emergency_Routes not found.")


# ---------------------------------------------------------------------------
# 8. Optimal emergency center summary
# ---------------------------------------------------------------------------
if arcpy.Exists(OPTIMAL_CENTERS):
    facility_type_field = find_field(OPTIMAL_CENTERS, ["facilitytype", "facility_type"])
    existing_count = 0
    new_count = 0

    if facility_type_field:
        with arcpy.da.SearchCursor(OPTIMAL_CENTERS, [facility_type_field]) as cursor:
            for (facility_type,) in cursor:
                if facility_type == 1:
                    existing_count += 1
                else:
                    new_count += 1
    else:
        hospital_count = int(arcpy.management.GetCount(HOSPITALS)[0]) if arcpy.Exists(HOSPITALS) else 0
        total_centers = int(arcpy.management.GetCount(OPTIMAL_CENTERS)[0])
        existing_count = min(hospital_count, total_centers)
        new_count = max(total_centers - existing_count, 0)

    candidate_count = int(arcpy.management.GetCount(CANDIDATE_LOCATIONS)[0]) if arcpy.Exists(CANDIDATE_LOCATIONS) else 0

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    axes[0].pie(
        [existing_count, new_count],
        labels=["Existing Hospitals", "New Selected Centers"],
        colors=["#457b9d", "#e63946"],
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops={"edgecolor": "white"},
    )
    axes[0].set_title("Optimal Center Composition", fontsize=12, weight="bold")

    bars = axes[1].bar(
        ["Candidate Locations", "New Selected Centers"],
        [candidate_count, new_count],
        color=["#8d99ae", "#e63946"],
        edgecolor="black",
    )
    axes[1].set_title("Candidate vs Selected New Centers", fontsize=12, weight="bold")
    axes[1].set_ylabel("Count")
    label_bars(axes[1], bars, "{:.0f}")

    plt.suptitle("Objective 3: Emergency Center Planning", fontsize=14, weight="bold")
    plt.tight_layout()
    save_figure(fig, "08_optimal_center_summary.png")
else:
    print("Skipped optimal center graph: Optimal_Emergency_Centers not found.")


# ---------------------------------------------------------------------------
# 9. Flood depth vs safe speed scatter
# ---------------------------------------------------------------------------
if road_rows:
    depths = []
    speeds = []
    for _status, depth, speed, _small, _amb, _heavy, _length_m in road_rows:
        if depth is not None and speed is not None:
            depths.append(float(depth))
            speeds.append(float(speed))

    if depths and speeds:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(depths, speeds, s=18, alpha=0.35, c="#264653", edgecolors="none")
        ax.axvline(0.20, color="#f4a261", linestyle="--", linewidth=1.5, label="Instability depth: 0.20 m")
        ax.axvline(0.35, color="#e76f51", linestyle="--", linewidth=1.5, label="Ambulance threshold: 0.35 m")
        ax.axvline(0.45, color="#c1121f", linestyle="--", linewidth=1.5, label="Heavy vehicle threshold: 0.45 m")
        ax.set_title("Flood Depth vs Safe Speed", fontsize=13, weight="bold")
        ax.set_xlabel("Flood Depth on Road (m)")
        ax.set_ylabel("Safe Speed (km/h)")
        ax.legend()
        plt.tight_layout()
        save_figure(fig, "09_depth_vs_safe_speed.png")


# ---------------------------------------------------------------------------
# 10. Summary dashboard
# ---------------------------------------------------------------------------
if road_rows and arcpy.Exists(FLOOD_RISK_ZONES):
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))

    # Flood zone area
    zone_labels = ["Red", "Orange", "Yellow", "Green"]
    zone_keys = [3, 2, 1, 0]
    zone_colors = ["#c1121f", "#f77f00", "#fcbf49", "#2a9d8f"]
    zone_areas = []
    temp_area = {3: 0.0, 2: 0.0, 1: 0.0, 0: 0.0}
    with arcpy.da.SearchCursor(FLOOD_RISK_ZONES, ["gridcode", "SHAPE@AREA"]) as cursor:
        for gridcode, area_m2 in cursor:
            if gridcode in temp_area:
                temp_area[gridcode] += area_m2 / 1e6
    zone_areas = [temp_area[key] for key in zone_keys]
    axes[0, 0].bar(zone_labels, zone_areas, color=zone_colors, edgecolor="black")
    axes[0, 0].set_title("Flood Risk Area (sq km)")

    # Road status count
    status_order = ["Safe", "Caution", "Restricted", "Impassable"]
    status_counts = {status: 0 for status in status_order}
    for status, _depth, _speed, _small, _amb, _heavy, _length_m in road_rows:
        if status in status_counts:
            status_counts[status] += 1
    axes[0, 1].bar(
        status_order,
        [status_counts[s] for s in status_order],
        color=["#2a9d8f", "#f4d35e", "#f4a261", "#c1121f"],
        edgecolor="black",
    )
    axes[0, 1].set_title("Road Status Count")
    axes[0, 1].tick_params(axis="x", rotation=15)

    # Speed class length
    speed_order = ["60-87 km/h", "40-60 km/h", "20-40 km/h", "10-20 km/h", "0-10 km/h", "0 km/h"]
    speed_lengths = {label: 0.0 for label in speed_order}
    for _status, _depth, safe_speed, _small, _amb, _heavy, length_m in road_rows:
        speed_lengths[classify_speed(safe_speed)] += (length_m or 0.0) / 1000.0
    axes[1, 0].bar(
        speed_order,
        [speed_lengths[s] for s in speed_order],
        color=["#2a9d8f", "#52b788", "#ffd166", "#f4a261", "#e76f51", "#c1121f"],
        edgecolor="black",
    )
    axes[1, 0].set_title("Road Length by Safe Speed Class")
    axes[1, 0].tick_params(axis="x", rotation=20)

    # Vehicle passability
    vehicle_labels = ["Small", "Ambulance", "Heavy"]
    passable_counts = [0, 0, 0]
    for row in road_rows:
        if row[3] == "Passable":
            passable_counts[0] += 1
        if row[4] == "Passable":
            passable_counts[1] += 1
        if row[5] == "Passable":
            passable_counts[2] += 1
    axes[1, 1].bar(vehicle_labels, passable_counts, color="#2a9d8f", edgecolor="black")
    axes[1, 1].set_title("Passable Segments by Vehicle Type")

    plt.suptitle("Emergency Routing Summary Dashboard", fontsize=16, weight="bold")
    plt.tight_layout()
    save_figure(fig, "10_summary_dashboard.png")


print("")
print("=" * 70)
print("GRAPH GENERATION COMPLETE")
print("=" * 70)
if saved_graphs:
    print("Saved files:")
    for graph_path in saved_graphs:
        print(f"  - {graph_path}")
else:
    print("No graphs were saved. Check whether the analysis outputs exist.")
