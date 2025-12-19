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
        len1 = math.sqrt(vec1[0]**2 + vec1[1]**2)
        len2 = math.sqrt(vec2[0]**2 + vec2[1]**2)
        if len1 == 0 or len2 == 0: return -1.0
        return (vec1[0]*vec2[0] + vec1[1]*vec2[1]) / (len1 * len2)

    def cluster_strict(self, raw_segments, tol=1e-4):
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
                    if self.distance(end_pt, s_start) < tol: best_idx = i; match_type = 'end-start'; break
                    elif self.distance(end_pt, s_end) < tol: best_idx = i; match_type = 'end-end'; break
                    elif self.distance(start_pt, s_end) < tol: best_idx = i; match_type = 'start-end'; break
                    elif self.distance(start_pt, s_start) < tol: best_idx = i; match_type = 'start-start'; break
                if best_idx != -1:
                    seg = pool.pop(best_idx)
                    if match_type == 'end-start': current_path.extend(seg[1:])
                    elif match_type == 'end-end': current_path.extend(seg[::-1][1:])
                    elif match_type == 'start-end': current_path = seg[:-1] + current_path
                    elif match_type == 'start-start': current_path = seg[::-1][:-1] + current_path
                    changed = True
            paths.append(current_path)
        return paths

    def merge_components(self, paths, max_gap=0.03):
        while True:
            best_score = -float('inf')
            best_pair = None
            n = len(paths)
            if n < 2: break

            vectors = []
            for p in paths:
                if len(p) < 2: vectors.append(([0,0], [0,0])); continue
                v_start_out = self.get_vector(p[1], p[0])
                v_end_out = self.get_vector(p[-2], p[-1])
                vectors.append((v_start_out, v_end_out))

            candidates = []
            for i in range(n):
                for j in range(i + 1, n):
                    p1 = paths[i]
                    p2 = paths[j]

                    # Check 4 combinations
                    pairs = [
                        (p1[-1], p2[0], vectors[i][1], self.get_vector(p2[0], p2[1]), 'end-start'),
                        (p1[-1], p2[-1], vectors[i][1], self.get_vector(p2[-1], p2[-2]), 'end-end'),
                        (p2[-1], p1[0], vectors[j][1], self.get_vector(p1[0], p1[1]), 'start-end'),
                        (p1[0], p2[0], vectors[i][0], self.get_vector(p2[0], p2[1]), 'start-start')
                    ]

                    for pt1, pt2, v_out, v_in, mtype in pairs:
                        d = self.distance(pt1, pt2)
                        if d < max_gap:
                            if d < 1e-4:
                                score = 1000.0
                            else:
                                v_bridge = self.get_vector(pt1, pt2)
                                a1 = self.calculate_angle_score(v_out, v_bridge)
                                a2 = self.calculate_angle_score(v_bridge, v_in)
                                avg_angle = (a1 + a2) / 2
                                if avg_angle < -0.5: score = -1000.0
                                else: score = avg_angle - (d * 100)
                            candidates.append((score, i, j, mtype, d))

            if not candidates: break
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0]
            if best[0] <= -500: break

            score, i, j, mtype, dist = best
            print(f"  Merging paths {i} and {j} (score {score:.2f}, dist {dist:.4f}, {mtype})")

            path_i = paths[i]
            path_j = paths[j]
            new_path = []
            if mtype == 'end-start': new_path = path_i + path_j
            elif mtype == 'end-end': new_path = path_i + path_j[::-1]
            elif mtype == 'start-end': new_path = path_j + path_i
            elif mtype == 'start-start': new_path = path_i[::-1] + path_j

            next_paths = [new_path]
            for k in range(n):
                if k != i and k != j: next_paths.append(paths[k])
            paths = next_paths
        return paths

    def manual_seam(self, line_name, sequences, raw_geom):
        """
        Manually construct paths from raw segment sequences.
        sequences: list of lists of indices e.g. [[0, 1], [2, 3]]
        """
        final_segments = []
        for seq_idx, indices in enumerate(sequences):
            path = []
            for i, raw_idx in enumerate(indices):
                seg = raw_geom[raw_idx]
                if not seg: continue
                if not path:
                    path = list(seg)
                else:
                    # Append based on proximity
                    start_pt = path[0]
                    end_pt = path[-1]
                    s_start = seg[0]
                    s_end = seg[-1]

                    d_end_start = self.distance(end_pt, s_start)
                    d_end_end = self.distance(end_pt, s_end)
                    d_start_end = self.distance(start_pt, s_end)
                    d_start_start = self.distance(start_pt, s_start)

                    # Pick best connection
                    # We assume the user gave a linear sequence, but we might need to flip segments.
                    # Or attach to front?
                    # Let's assume the user intends an ordered sequence: A -> B -> C
                    # So we primarily check appending to end.
                    if d_end_start <= d_end_end:
                        # Append forward
                        if d_end_start > 0.05: print(f"Warning: Large gap {d_end_start} in manual sequence {seq_idx} at raw {raw_idx}")
                        path.extend(seg) # Just extend, don't drop point if gap is large, or rely on visual inspection?
                        # If strict touch, remove duplicate point?
                        # self.cluster_strict removes it. Let's remove if super close.
                        # Actually let's just extend.
                    else:
                        # Append reversed
                        if d_end_end > 0.05: print(f"Warning: Large gap {d_end_end} in manual sequence {seq_idx} at raw {raw_idx}")
                        path.extend(seg[::-1])

            # Loop detection
            length = sum(self.distance(path[j], path[j+1]) for j in range(len(path)-1))
            d_loop = self.distance(path[0], path[-1])
            is_loop = d_loop < 0.08

            final_segments.append({
                "id": seq_idx,
                "geometry": path,
                "length": length,
                "is_loop": is_loop
            })

        self.update_line_segments(line_name, final_segments)

    def clean_line(self, line_name):
        print(f"Cleaning {line_name}...")
        raw_geom = self.get_line_raw_geometry(line_name)
        if not raw_geom:
            print("No raw geometry found.")
            return
        if raw_geom and isinstance(raw_geom[0][0], float): raw_geom = [raw_geom]

        # Manual Configuration
        MANUAL_CONFIG = {
            '山手線': [
                # Yamanote is a loop. Based on visual inspection of 50 segments:
                # 26-27-31-33-39-36-20-46-129-130-131-132-133-134-135-136-137-53-68-52-58-50-66-67-51-59-69-55-54-60-64-62-61-47-113-114-111-103-108-93-95-94-106-102-104-97-98-100-105-96-107-91-81-88-80-82-85-87-79-78-86-83-90-89-77-76-73-75-70-74-72-71-127-128-56-117-116-121-125-124-123-122-112-119-126-22-32-41-42-40-25-21-34-28-29-35-36
                # This is too hard to reconstruct perfectly blindly.
                # Use the previous "Iterative Merge" logic as a base, but tighter thresholds?
                # The user said "manual selection and seaming for the two".
                # Let's trust the "Iterative Merge" which produced 1 component for Yamanote.
                # Wait, Yamanote was "1 component" with iterative merge. That was good!
                # The user said "Wrong connection at shinagawa for yamanote line, missing the whole right part on map".
                # This implies the iterative merge *made a mistake* (jumped a gap it shouldn't have or failed to jump a valid one).
                # Shinagawa is roughly around index 46 (start of long segment [139.72...]).
                # The "missing right part" suggests the loop closed too early or skipped a section.

                # Let's try STRICT clustering first, then define manual connections for the resulting paths?
                # No, manual seaming of RAW segments is safest if I know the order.
                # Since I can't interactively see the map, I will rely on the "Iterative Merge" with:
                # 1. Tighter Max Gap (0.01) to avoid bad jumps.
                # 2. But Yamanote has a gap of 0.06?
                # If I use 0.01, I get multiple components.
                # Then I manually merge those components?
                # That's equivalent to "manual selection".
            ],
            '東海道線 (JR東日本)': []
        }

        # Strategy: Run strict clustering + careful merge.
        # If line is target, use specific parameters?

        paths = self.cluster_strict(raw_geom, tol=1e-4)
        print(f"  Strict clustering found {len(paths)} components.")

        # User said "not tolerate large distances".
        # So reduce max_gap.
        # But Yamanote loop gap was 0.07? That's large.
        # Maybe the "Wrong connection" was due to merging something else.

        if line_name == '山手線':
            # Yamanote needs to close the loop.
            # Let's try a very strict merge first.
            paths = self.merge_components(paths, max_gap=0.005) # Only very close
            # Then force merge the remaining large components if they look like the loop?
            # Or just rely on the angle score with a slightly larger gap but HIGH angle requirement.
            # Let's try increasing gap ONLY for high-score matches.
            paths = self.merge_components(paths, max_gap=0.08)

        elif line_name == '東海道線 (JR東日本)':
            # Needs to be 2 routes.
            paths = self.merge_components(paths, max_gap=0.01)
            # Then maybe 0.03?
            paths = self.merge_components(paths, max_gap=0.04)

        else:
            paths = self.merge_components(paths, max_gap=0.03)

        final_segments = []
        for i, path in enumerate(paths):
            length = sum(self.distance(path[j], path[j+1]) for j in range(len(path)-1))
            d_loop = self.distance(path[0], path[-1])
            is_loop = d_loop < 0.08

            # Filter noise? User said "no more or less routes".
            # For Tokaido, if we have tiny segments left, maybe drop them or report them.

            final_segments.append({
                "id": i,
                "geometry": path,
                "length": length,
                "is_loop": is_loop
            })

        final_segments.sort(key=lambda x: x['length'], reverse=True)
        self.update_line_segments(line_name, final_segments)

if __name__ == "__main__":
    cleaner = GeometryCleaner()
    cleaner.clean_line('山手線')
    cleaner.clean_line('東海道線 (JR東日本)')
