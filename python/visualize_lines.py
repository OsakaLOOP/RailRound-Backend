import sqlite3
import json
import os

def create_visualization(line_name, output_file):
    print(f"Generating visualization for {line_name}...")

    db_path = "railway.db"
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT segments FROM lines WHERE name = ?", (line_name,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        print(f"No segments found for {line_name}")
        return

    segments = json.loads(row[0])

    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Visualization: {line_name}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        #map {{ height: 100vh; }}
        body {{ margin: 0; padding: 0; }}
        .info-box {{
            position: absolute; top: 10px; right: 10px; z-index: 1000;
            background: white; padding: 10px; border: 1px solid #ccc;
            max-height: 90vh; overflow-y: auto;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="info-box">
        <h3>{line_name}</h3>
        <div id="segment-list"></div>
    </div>
    <script>
        var map = L.map('map').setView([35.68, 139.76], 10);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        var colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'magenta', 'lime'];
        var segments = {json.dumps(segments)};
        var bounds = L.latLngBounds();

        segments.forEach(function(seg, index) {{
            var coords = seg.geometry.map(function(p) {{ return [p[1], p[0]]; }});
            if (coords.length === 0) return;

            var color = colors[index % colors.length];
            var polyline = L.polyline(coords, {{color: color, weight: 5, opacity: 0.7}}).addTo(map);
            bounds.extend(polyline.getBounds());

            // Markers for start/end
            L.circleMarker(coords[0], {{color: 'black', fillColor: 'white', fillOpacity: 1, radius: 5}}).addTo(map)
             .bindPopup('Path ' + index + ' Start');
            L.circleMarker(coords[coords.length - 1], {{color: 'black', fillColor: color, fillOpacity: 1, radius: 5}}).addTo(map)
             .bindPopup('Path ' + index + ' End');

            var div = document.createElement('div');
            div.style.color = color;
            div.innerHTML = '<strong>Path ' + index + '</strong>: Len=' + seg.length.toFixed(4) + (seg.is_loop ? ' (Loop)' : '');
            document.getElementById('segment-list').appendChild(div);
        }});

        if (segments.length > 0) {{
            map.fitBounds(bounds);
        }}
    </script>
</body>
</html>
    """

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Saved to {output_file}")

if __name__ == "__main__":
    if not os.path.exists("public"):
        os.makedirs("public")
    create_visualization("山手線", "public/yamanote_debug.html")
    create_visualization("東海道線 (JR東日本)", "public/tokaido_debug.html")
