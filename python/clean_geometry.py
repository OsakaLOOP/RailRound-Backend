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

    def cluster_strict(self, raw_segments, tol=1e-4):
        """
        Merges segments that strictly touch (within tolerance).
        Returns a list of lists of points (paths).
        """
        # Convert all to lists
        pool = [s for s in raw_segments if len(s) > 0]
        paths = []

        while pool:
            current_path = pool.pop(0)
            changed = True

            while changed:
                changed = False
                start_pt = current_path[0]
                end_pt = current_path[-1]

                best_idx = -1
                match_type = None

                for i, seg in enumerate(pool):
                    s_start = seg[0]
                    s_end = seg[-1]

                    if self.distance(end_pt, s_start) < tol:
                        best_idx = i; match_type = 'end-start'; break
                    elif self.distance(end_pt, s_end) < tol:
                        best_idx = i; match_type = 'end-end'; break
                    elif self.distance(start_pt, s_end) < tol:
                        best_idx = i; match_type = 'start-end'; break
                    elif self.distance(start_pt, s_start) < tol:
                        best_idx = i; match_type = 'start-start'; break

                if best_idx != -1:
                    seg = pool.pop(best_idx)
                    if match_type == 'end-start':
                        current_path.extend(seg[1:])
                    elif match_type == 'end-end':
                        current_path.extend(seg[::-1][1:])
                    elif match_type == 'start-end':
                        current_path = seg[:-1] + current_path
                    elif match_type == 'start-start':
                        current_path = seg[::-1][:-1] + current_path
                    changed = True

            paths.append(current_path)
        return paths

    def merge_components(self, paths, max_gap=0.03):
        """
        Iteratively merges the closest pair of path endpoints.
        """
        # We work with indices into 'paths' list
        # active_indices tracks which paths are still valid (not merged into another)
        # However, modifying the list is tricky. Let's use a while loop and reconstruct.

        while True:
            best_dist = float('inf')
            best_pair = None # (i, j, match_type)

            n = len(paths)
            if n < 2: break

            for i in range(n):
                for j in range(i + 1, n):
                    p1 = paths[i]
                    p2 = paths[j]

                    # 4 combinations
                    d1 = self.distance(p1[-1], p2[0]) # end-start
                    if d1 < best_dist: best_dist = d1; best_pair = (i, j, 'end-start')

                    d2 = self.distance(p1[-1], p2[-1]) # end-end
                    if d2 < best_dist: best_dist = d2; best_pair = (i, j, 'end-end')

                    d3 = self.distance(p1[0], p2[-1]) # start-end
                    if d3 < best_dist: best_dist = d3; best_pair = (i, j, 'start-end')

                    d4 = self.distance(p1[0], p2[0]) # start-start
                    if d4 < best_dist: best_dist = d4; best_pair = (i, j, 'start-start')

            if best_pair and best_dist < max_gap:
                i, j, mtype = best_pair
                print(f"  Merging paths {i} and {j} (gap {best_dist:.4f}, {mtype})")

                path_i = paths[i]
                path_j = paths[j]

                new_path = []
                if mtype == 'end-start':
                    new_path = path_i + path_j
                elif mtype == 'end-end':
                    new_path = path_i + path_j[::-1]
                elif mtype == 'start-end':
                    new_path = path_j + path_i
                elif mtype == 'start-start':
                    new_path = path_j[::-1] + path_i

                # Replace path i with new_path, remove path j
                # Careful with indices. We reconstruct the list.
                next_paths = []
                next_paths.append(new_path)
                for k in range(n):
                    if k != i and k != j:
                        next_paths.append(paths[k])
                paths = next_paths
            else:
                break

        return paths

    def clean_line(self, line_name):
        print(f"Cleaning {line_name}...")
        raw_geom = self.get_line_raw_geometry(line_name)
        if not raw_geom:
            print("No raw geometry found.")
            return

        if raw_geom and isinstance(raw_geom[0][0], float):
             raw_geom = [raw_geom]

        # 1. Strict Cluster
        paths = self.cluster_strict(raw_geom, tol=1e-4)
        print(f"  Strict clustering found {len(paths)} components.")

        # 2. Merge Components (Gap Bridging)
        # Using 0.03 (~3km) as a safe heuristic for rail gaps
        paths = self.merge_components(paths, max_gap=0.03)
        print(f"  After merging: {len(paths)} components.")

        # 3. Finalize
        final_segments = []
        for i, path in enumerate(paths):
            length = sum(self.distance(path[j], path[j+1]) for j in range(len(path)-1))

            # Loop detection
            d_loop = self.distance(path[0], path[-1])
            is_loop = d_loop < 0.08 # Tolerance for closing loop

            if is_loop:
                print(f"  Path {i}: Detected loop gap {d_loop:.4f}. Leaving cut.")
                # We do not append the point, keeping it a LineString "cut" at the gap.

            print(f"  Path {i}: {len(path)} points, Length ~{length:.4f}, Loop: {is_loop}")

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
