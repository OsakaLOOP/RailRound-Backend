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

    def calculate_angle_score(self, vec1, vec2):
        """
        Calculate cosine of the angle between two vectors.
        Returns a value between -1.0 (180 deg) and 1.0 (0 deg).
        Closer to 1.0 means smoother continuation.
        """
        # Normalize vectors
        len1 = math.sqrt(vec1[0]**2 + vec1[1]**2)
        len2 = math.sqrt(vec2[0]**2 + vec2[1]**2)

        if len1 == 0 or len2 == 0:
            return -1.0 # Treat zero length vectors as bad matches

        return (vec1[0]*vec2[0] + vec1[1]*vec2[1]) / (len1 * len2)

    def get_vector(self, p_start, p_end):
        return [p_end[0] - p_start[0], p_end[1] - p_start[1]]

    def seam_segments(self, raw_segments):
        # raw_segments is a list of lists of points [[x,y], ...]
        if not raw_segments:
            return []

        # Convert all segments to lists of points (if they aren't already)
        pool = [s for s in raw_segments if s]
        paths = []

        while pool:
            # Start a new path with the first segment in the pool
            # Heuristic: picking longest segment first might be better,
            # but let's stick to first available for stability unless optimized further.
            current_path = pool.pop(0)
            changed = True

            while changed:
                changed = False

                # Check connection at START of path
                start_pt = current_path[0]
                # Check connection at END of path
                end_pt = current_path[-1]

                best_match_idx = -1
                best_match_score = -2.0 # Cosine similarity range is [-1, 1]
                match_type = None # 'start-start', 'start-end', 'end-start', 'end-end'

                # Tolerance for float comparison (approx 11m if lat/lon)
                tol = 1e-4

                # Vectors for current path ends
                # Start vector: pointing INWARDS from start (p1 -> p0 is outward, we want inward flow p0->p1? No, we want continuity)
                # If we extend backwards from start: new_seg -> current_path
                # Vector leaving new_seg = (new_end - new_prev)
                # Vector entering current_path = (curr_1 - curr_0)
                # We want these to align.

                if len(current_path) >= 2:
                    vec_start_out = self.get_vector(current_path[1], current_path[0]) # Pointing out from start
                    vec_end_out = self.get_vector(current_path[-2], current_path[-1]) # Pointing out from end
                else:
                    vec_start_out = [0, 0]
                    vec_end_out = [0, 0]

                for i, seg in enumerate(pool):
                    if len(seg) < 2: continue # Ignore single points

                    s_start = seg[0]
                    s_end = seg[-1]

                    # Candidate 1: Connect seg start to path end (end-start)
                    if self.distance(end_pt, s_start) < tol:
                        # Vector entering junction from path: vec_end_out
                        # Vector leaving junction into seg: s[1] - s[0]
                        vec_seg_in = self.get_vector(s_start, seg[1])
                        score = self.calculate_angle_score(vec_end_out, vec_seg_in)

                        if score > best_match_score:
                            best_match_score = score
                            best_match_idx = i
                            match_type = 'end-start'

                    # Candidate 2: Connect seg end to path end (end-end) -> Reverse seg
                    if self.distance(end_pt, s_end) < tol:
                        # Vector leaving junction into reversed seg: s[-2] - s[-1]
                        vec_seg_in = self.get_vector(s_end, seg[-2])
                        score = self.calculate_angle_score(vec_end_out, vec_seg_in)

                        if score > best_match_score:
                            best_match_score = score
                            best_match_idx = i
                            match_type = 'end-end'

                    # Candidate 3: Connect seg end to path start (start-end)
                    if self.distance(start_pt, s_end) < tol:
                        # Vector leaving junction into path: vec_start_in = (curr[1] - curr[0]) -- wait, logic inverse
                        # We are moving form seg -> path.
                        # Vector exiting seg: s_end - s_prev
                        # Vector entering path: curr[1] - curr[0] (which is -vec_start_out)
                        vec_seg_out = self.get_vector(seg[-2], s_end)
                        vec_path_in = self.get_vector(start_pt, current_path[1])
                        score = self.calculate_angle_score(vec_seg_out, vec_path_in)

                        if score > best_match_score:
                            best_match_score = score
                            best_match_idx = i
                            match_type = 'start-end'

                    # Candidate 4: Connect seg start to path start (start-start) -> Reverse seg
                    if self.distance(start_pt, s_start) < tol:
                        # Vector exiting reversed seg: s_start - s_next
                        vec_seg_out = self.get_vector(seg[1], s_start)
                        vec_path_in = self.get_vector(start_pt, current_path[1])
                        score = self.calculate_angle_score(vec_seg_out, vec_path_in)

                        if score > best_match_score:
                            best_match_score = score
                            best_match_idx = i
                            match_type = 'start-start'

                # Apply the best match if one exists
                # We can enforce a minimum score if we want to avoid sharp turns, e.g. > -0.5
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
            is_loop = self.distance(path[0], path[-1]) < 1e-4

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
