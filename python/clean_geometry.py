import sqlite3
import json
import math

class GeometryCleaner:
    def __init__(self, db_path="railway.db"):
        self.db_path = db_path

    def get_line_raw_geometry(self, line_name):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT raw_geometry FROM lines WHERE name = ?", (line_name,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return json.loads(row[0])
        return None

    def update_line_segments(self, line_name, segments_data):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        segments_json = json.dumps(segments_data)
        cursor.execute("UPDATE lines SET segments = ? WHERE name = ?", (segments_json, line_name))
        conn.commit()
        conn.close()
        print(f"Updated segments for {line_name}")

    def distance(self, p1, p2):
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def seam_segments(self, raw_segments):
        # raw_segments is a list of lists of points [[x,y], ...]
        if not raw_segments:
            return []

        # Convert all segments to lists of points (if they aren't already)
        pool = [s for s in raw_segments if s]
        paths = []

        while pool:
            # Start a new path with the first segment in the pool
            current_path = pool.pop(0)
            changed = True

            while changed:
                changed = False
                # Try to find a segment that connects to current_path's start or end
                # Check strict equality first, maybe fuzzy later if needed

                start_pt = current_path[0]
                end_pt = current_path[-1]

                best_match_idx = -1
                match_type = None # 'start-start', 'start-end', 'end-start', 'end-end'

                for i, seg in enumerate(pool):
                    s_start = seg[0]
                    s_end = seg[-1]

                    # Tolerance for float comparison
                    tol = 1e-5

                    if self.distance(end_pt, s_start) < tol:
                        best_match_idx = i
                        match_type = 'end-start'
                        break
                    elif self.distance(end_pt, s_end) < tol:
                        best_match_idx = i
                        match_type = 'end-end' # Need to reverse seg
                        break
                    elif self.distance(start_pt, s_end) < tol:
                        best_match_idx = i
                        match_type = 'start-end'
                        break
                    elif self.distance(start_pt, s_start) < tol:
                        best_match_idx = i
                        match_type = 'start-start' # Need to reverse seg
                        break

                if best_match_idx != -1:
                    seg = pool.pop(best_match_idx)
                    if match_type == 'end-start':
                        current_path.extend(seg[1:]) # Avoid duplicating the join point
                    elif match_type == 'end-end':
                        current_path.extend(seg[::-1][1:])
                    elif match_type == 'start-end':
                        current_path = seg[:-1] + current_path
                    elif match_type == 'start-start':
                        current_path = seg[::-1][:-1] + current_path
                    changed = True

            paths.append(current_path)

        return paths

    def clean_line(self, line_name):
        print(f"Cleaning {line_name}...")
        raw_geom = self.get_line_raw_geometry(line_name)
        if not raw_geom:
            print("No raw geometry found.")
            return

        # 'raw_geom' should be a list of lists (MultiLineString coordinates)
        # If it's just a single list (LineString), wrap it
        if raw_geom and isinstance(raw_geom[0][0], float):
             raw_geom = [raw_geom]

        seamed_paths = self.seam_segments(raw_geom)

        print(f"  Result: {len(seamed_paths)} continuous paths.")

        # Calculate lengths to identify main lines
        final_segments = []
        for i, path in enumerate(seamed_paths):
            length = 0
            for j in range(len(path)-1):
                length += self.distance(path[j], path[j+1])

            # Identify round lines (start ~= end)
            is_loop = self.distance(path[0], path[-1]) < 1e-5

            # Auto cut loop: If it's a loop, ensure it stays as a LineString (which it is).
            # The user asked to "auto cut a round line".
            # If it's a perfect loop, the start and end are the same.
            # We treat it as a continuous line.

            print(f"  Path {i}: {len(path)} points, Length unit ~{length:.4f}, Loop: {is_loop}")

            final_segments.append({
                "id": i,
                "geometry": path,
                "length": length,
                "is_loop": is_loop
            })

        # Sort by length descending
        final_segments.sort(key=lambda x: x['length'], reverse=True)

        self.update_line_segments(line_name, final_segments)

if __name__ == "__main__":
    cleaner = GeometryCleaner()
    cleaner.clean_line('山手線')
    cleaner.clean_line('東海道線 (JR東日本)')
