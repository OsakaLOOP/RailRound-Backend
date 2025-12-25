import json
import logging
import os
from shapely.geometry import shape, MultiLineString
from line_segmenter import LineSegmenter
import sys

# Optional dependency for visualization
try:
    import folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

# Pywebview dependency
try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestSegmentation")

def load_geojson(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_test():
    filepath = "public/geojson/東日本旅客鉄道.geojson"
    target_line_name = "東海道線 (JR東日本)"

    logger.info(f"Loading {filepath}...")
    try:
        data = load_geojson(filepath)
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        return

    # Extract Line and Stations
    line_feature = None
    stations = []

    for feature in data['features']:
        props = feature.get('properties', {})
        if props.get('name') == target_line_name and props.get('type') == 'line':
            line_feature = feature
        elif props.get('line') == target_line_name and props.get('type') == 'station':
            # Create simple station dict
            geom = feature.get('geometry')
            if geom and geom['type'] == 'Point':
                stations.append({
                    'name': props.get('name'),
                    'location': shape(geom)
                })

    if not line_feature:
        logger.error(f"Line '{target_line_name}' not found!")
        return

    logger.info(f"Found line: {target_line_name}")
    logger.info(f"Found {len(stations)} stations associated with the line.")

    line_geometry = shape(line_feature['geometry'])

    # Run Segmentation
    logger.info("Initializing LineSegmenter...")
    segmenter = LineSegmenter(line_geometry, stations)

    logger.info("Running segmentation...")
    segments = segmenter.segment()

    logger.info(f"Segmentation complete. Found {len(segments)} segments.")

    # Print Connectivity Graph
    print("\n--- Connectivity Graph ---")
    for (start, end), geom in segments.items():
        print(f"{start} <--> {end} : Length approx {geom.length:.5f} deg")

    # Generate Visualization
    output_path = os.path.abspath("public/debug_segmentation.html")

    if FOLIUM_AVAILABLE:
        visualize(line_geometry, segments, segmenter.debug_partial_segments, stations, segmenter.debug_knives, output_path)

        # Open in Webview
        if WEBVIEW_AVAILABLE:
            logger.info("Opening visualization in window...")
            webview.create_window("Segmentation Debug", f"file://{output_path}", frameless=False, fullscreen=False)
            webview.start()
        else:
            logger.info(f"Pywebview not available. Open {output_path} manually.")
    else:
        logger.warning("Folium not installed. Skipping visualization.")

def visualize(original_geometry, segments, partial_segments, stations, knives, output_path):
    # Calculate center for map
    center_pt = original_geometry.centroid
    m = folium.Map(location=[center_pt.y, center_pt.x], zoom_start=10)

    # Add original geometry (grey, thin)
    folium.GeoJson(
        original_geometry,
        style_function=lambda x: {'color': '#999', 'weight': 2, 'opacity': 0.3}
    ).add_to(m)

    # Add knives (Red)
    if knives:
        folium.GeoJson(
            MultiLineString(knives),
            style_function=lambda x: {'color': 'red', 'weight': 2, 'opacity': 1}
        ).add_to(m)

    # Add Valid Segments (Green)
    for (start, end), geom in segments.items():
        folium.GeoJson(
            geom,
            style_function=lambda x: {'color': 'green', 'weight': 5, 'opacity': 0.8},
            tooltip=f"VALID: {start} - {end}"
        ).add_to(m)

    # Add Partial Segments
    for p in partial_segments:
        if p['start'] and p['end']:
            continue

        color = 'gray'
        tooltip = "None"

        if p['start']:
            color = 'blue' # Start Only
            tooltip = f"Start: {p['start']}"
        elif p['end']:
            color = 'orange' # End Only
            tooltip = f"End: {p['end']}"
        else:
            color = 'black' # None
            tooltip = "Unconnected"

        folium.GeoJson(
            p['geometry'],
            style_function=lambda x, color=color: {'color': color, 'weight': 3, 'opacity': 0.8},
            tooltip=tooltip
        ).add_to(m)

    # Add stations
    for s in stations:
        folium.CircleMarker(
            location=[s['location'].y, s['location'].x],
            radius=4,
            color='white',
            fill=True,
            fill_color='black',
            popup=s['name']
        ).add_to(m)

    m.save(output_path)
    logger.info(f"Visualization saved to {output_path}")

if __name__ == "__main__":
    run_test()
