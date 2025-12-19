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

    def get_vector(self, p_start, p_end):
        return [p_end[0] - p_start[0], p_end[1] - p_start[1]]

    def calculate_angle_score(self, vec1, vec2):
        """
        Calculate cosine of the angle between two vectors.
        Returns a value between -1.0 (180 deg) and 1.0 (0 deg).
        Closer to 1.0 means smoother continuation.
        """
        len1 = math.sqrt(vec1[0]**2 + vec1[1]**2)
        len2 = math.sqrt(vec2[0]**2 + vec2[1]**2)

        if len1 == 0 or len2 == 0:
            return -1.0

        return (vec1[0]*vec2[0] + vec1[1]*vec2[1]) / (len1 * len2)

    def cluster_strict(self, raw_segments, tol=1e-4):
        """
        Merges segments that strictly touch (within tolerance).
        Returns a list of lists of points (paths).
        """
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

                # Strict clustering only checks distance
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
        Iteratively merges path endpoints considering distance AND angle.
        """
        while True:
            best_score = -float('inf') # We want to maximize score
            best_pair = None # (i, j, match_type, distance)

            n = len(paths)
            if n < 2: break

            # Precompute vectors for ends of all paths
            # vec_start: Entering the path at start (p1->p0) ? No, standard flow.
            # We need vectors pointing OUT from the endpoints to measure alignment with the connecting vector.
            # Out from End: p[-2] -> p[-1]
            # Out from Start: p[1] -> p[0]

            vectors = []
            for p in paths:
                if len(p) < 2:
                    vectors.append(([0,0], [0,0]))
                    continue
                v_start_out = self.get_vector(p[1], p[0])
                v_end_out = self.get_vector(p[-2], p[-1])
                vectors.append((v_start_out, v_end_out))

            candidates = []

            for i in range(n):
                for j in range(i + 1, n):
                    p1 = paths[i]
                    p2 = paths[j]

                    # 4 combinations
                    # 1. End of P1 -> Start of P2
                    d = self.distance(p1[-1], p2[0])
                    if d < max_gap:
                        # Vector P1_end -> P2_start (The gap bridge)
                        v_bridge = self.get_vector(p1[-1], p2[0])
                        # Angle 1: P1_end_out vs Bridge
                        a1 = self.calculate_angle_score(vectors[i][1], v_bridge)
                        # Angle 2: Bridge vs P2_start_in (which is -P2_start_out)
                        # v_bridge points INTO P2. P2_start_out points OUT of P2. They should be opposite?
                        # Ideally P1->Bridge->P2 is a line.
                        # P1_end_out aligned with Bridge aligned with (P2[0]->P2[1]) i.e. -P2_start_out.
                        v_p2_in = self.get_vector(p2[0], p2[1])
                        a2 = self.calculate_angle_score(v_bridge, v_p2_in)

                        # If distance is super small, angle matters less.
                        # If distance is large, angle implies continuity.

                        # Score: Minimize distance, Maximize angle.
                        # Let's normalize distance. 0.03 is max.
                        # dist_penalty = d / max_gap  (0 to 1)
                        # angle_bonus = (a1 + a2) / 2 ( -1 to 1)
                        # combined = angle_bonus - weight * dist_penalty

                        # However, if d is tiny (clustering missed it), angle is irrelevant (noise).
                        if d < 1e-4:
                            score = 1000.0 # Prioritize strict touches
                        else:
                            # We require decent angle alignment for gaps.
                            # If sharp turn (angle < 0), score is low.
                            avg_angle = (a1 + a2) / 2
                            if avg_angle < -0.5: # 120 deg turn?
                                score = -1000.0
                            else:
                                score = avg_angle - (d * 100) # Weight distance heavily

                        candidates.append((score, i, j, 'end-start', d))

                    # 2. End of P1 -> End of P2 (Reverse P2)
                    d = self.distance(p1[-1], p2[-1])
                    if d < max_gap:
                        v_bridge = self.get_vector(p1[-1], p2[-1])
                        a1 = self.calculate_angle_score(vectors[i][1], v_bridge)
                        # P2 reversed: Start is P2[-1], vector in is P2[-1]->P2[-2] (which is P2_end_out flipped)
                        v_p2_in = self.get_vector(p2[-1], p2[-2]) # = -v_end_out
                        a2 = self.calculate_angle_score(v_bridge, v_p2_in)

                        if d < 1e-4: score = 1000.0
                        else:
                            avg_angle = (a1 + a2) / 2
                            if avg_angle < -0.5: score = -1000.0
                            else: score = avg_angle - (d * 100)
                        candidates.append((score, i, j, 'end-end', d))

                    # 3. Start of P1 -> End of P2 (Reverse P1? No, P2->P1)
                    # We treat merge as symmetric, just removing one.
                    # P2 End -> P1 Start
                    d = self.distance(p2[-1], p1[0])
                    if d < max_gap:
                        v_bridge = self.get_vector(p2[-1], p1[0])
                        a1 = self.calculate_angle_score(vectors[j][1], v_bridge) # P2 end out
                        v_p1_in = self.get_vector(p1[0], p1[1])
                        a2 = self.calculate_angle_score(v_bridge, v_p1_in)

                        if d < 1e-4: score = 1000.0
                        else:
                            avg_angle = (a1 + a2) / 2
                            if avg_angle < -0.5: score = -1000.0
                            else: score = avg_angle - (d * 100)
                        candidates.append((score, i, j, 'start-end', d)) # i is P1 (start), j is P2 (end) -> P2...P1

                    # 4. Start of P1 -> Start of P2
                    d = self.distance(p1[0], p2[0])
                    if d < max_gap:
                        # Connect P1[0] and P2[0]. One must reverse.
                        # Let's say we reverse P1. P1... -> P2...
                        # P1[1]->P1[0] (v_start_out) -> bridge -> P2[0]->P2[1]
                        v_bridge = self.get_vector(p1[0], p2[0])
                        a1 = self.calculate_angle_score(vectors[i][0], v_bridge)
                        v_p2_in = self.get_vector(p2[0], p2[1])
                        a2 = self.calculate_angle_score(v_bridge, v_p2_in)

                        if d < 1e-4: score = 1000.0
                        else:
                            avg_angle = (a1 + a2) / 2
                            if avg_angle < -0.5: score = -1000.0
                            else: score = avg_angle - (d * 100)
                        candidates.append((score, i, j, 'start-start', d))

            if not candidates:
                break

            # Sort by score descending
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0]

            # Threshold?
            if best[0] <= -500: # Threshold for "bad match" (large distance or terrible angle)
                break

            score, i, j, mtype, dist = best
            print(f"  Merging paths {i} and {j} (score {score:.2f}, dist {dist:.4f}, {mtype})")

            path_i = paths[i]
            path_j = paths[j]

            new_path = []
            if mtype == 'end-start': # i -> j
                new_path = path_i + path_j
            elif mtype == 'end-end': # i -> j(rev)
                new_path = path_i + path_j[::-1]
            elif mtype == 'start-end': # j -> i
                new_path = path_j + path_i
            elif mtype == 'start-start': # i(rev) -> j
                new_path = path_i[::-1] + path_j

            # Reconstruct list
            next_paths = [new_path]
            for k in range(n):
                if k != i and k != j:
                    next_paths.append(paths[k])
            paths = next_paths

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

        # 2. Merge Components (Gap Bridging with Angle)
        # Using slightly relaxed 0.05 (~5km) but relying on angle score to filter bad ones
        paths = self.merge_components(paths, max_gap=0.05)
        print(f"  After merging: {len(paths)} components.")

        # 3. Finalize
        final_segments = []
        for i, path in enumerate(paths):
            length = sum(self.distance(path[j], path[j+1]) for j in range(len(path)-1))

            # Loop detection
            d_loop = self.distance(path[0], path[-1])
            is_loop = d_loop < 0.08

            if is_loop:
                print(f"  Path {i}: Detected loop gap {d_loop:.4f}. Leaving cut.")

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
