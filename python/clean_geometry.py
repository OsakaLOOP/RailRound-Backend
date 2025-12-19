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

    def extend_seeds(self, paths, max_gap=0.03, min_alignment=0.0):
        print(f"Starting extend_seeds with {len(paths)} paths. Max gap: {max_gap}, Min align: {min_alignment}")

        pool = []
        for i, p in enumerate(paths):
            length = sum(self.distance(p[k], p[k+1]) for k in range(len(p)-1))
            pool.append({
                'id': i,
                'geometry': p,
                'length': length
            })

        final_paths = []

        while pool:
            pool.sort(key=lambda x: x['length'], reverse=True)
            seed = pool.pop(0)
            seed_geom = seed['geometry']

            extended = True
            while extended:
                extended = False
                best_match = None
                best_score = -float('inf')

                if len(seed_geom) < 2: break

                v_head_out = self.get_vector(seed_geom[1], seed_geom[0])
                v_tail_out = self.get_vector(seed_geom[-2], seed_geom[-1])
                seed_head = seed_geom[0]
                seed_tail = seed_geom[-1]

                for i, cand in enumerate(pool):
                    cand_geom = cand['geometry']
                    if len(cand_geom) < 2: continue

                    cand_head = cand_geom[0]
                    cand_tail = cand_geom[-1]
                    v_c_head_out = self.get_vector(cand_geom[1], cand_geom[0])
                    v_c_tail_out = self.get_vector(cand_geom[-2], cand_geom[-1])
                    v_c_head_in = self.get_vector(cand_geom[0], cand_geom[1])
                    v_c_tail_in = self.get_vector(cand_geom[-1], cand_geom[-2])
                    v_head_in = self.get_vector(seed_geom[0], seed_geom[1])

                    d_th = self.distance(seed_tail, cand_head)
                    d_tt = self.distance(seed_tail, cand_tail)
                    d_ct = self.distance(cand_tail, seed_head)
                    d_ch = self.distance(cand_head, seed_head)

                    # Logic: If distance is very small (< 0.01), ignore alignment check (assume continuous)
                    ignore_align_dist = 0.01

                    # 1. Tail-Head
                    if d_th < max_gap:
                        gap_v = self.get_vector(seed_tail, cand_head)
                        a1 = self.calculate_angle_score(v_tail_out, gap_v) if d_th > 1e-5 else 1.0
                        a2 = self.calculate_angle_score(gap_v, v_c_head_in) if d_th > 1e-5 else 1.0

                        if d_th < ignore_align_dist: a1=1.0; a2=1.0

                        if a1 > min_alignment and a2 > min_alignment:
                            score = (a1 + a2) - (math.exp(d_th * 50) - 1)
                            if score > best_score: best_score = score; best_match = (i, 'tail-head', score, d_th)

                    # 2. Tail-Tail
                    if d_tt < max_gap:
                        gap_v = self.get_vector(seed_tail, cand_tail)
                        a1 = self.calculate_angle_score(v_tail_out, gap_v) if d_tt > 1e-5 else 1.0
                        a2 = self.calculate_angle_score(gap_v, v_c_tail_in) if d_tt > 1e-5 else 1.0

                        if d_tt < ignore_align_dist: a1=1.0; a2=1.0

                        if a1 > min_alignment and a2 > min_alignment:
                            score = (a1 + a2) - (math.exp(d_tt * 50) - 1)
                            if score > best_score: best_score = score; best_match = (i, 'tail-tail', score, d_tt)

                    # 3. Cand Tail-Seed Head
                    if d_ct < max_gap:
                        gap_v = self.get_vector(cand_tail, seed_head)
                        a1 = self.calculate_angle_score(v_c_tail_out, gap_v) if d_ct > 1e-5 else 1.0
                        a2 = self.calculate_angle_score(gap_v, v_head_in) if d_ct > 1e-5 else 1.0

                        if d_ct < ignore_align_dist: a1=1.0; a2=1.0

                        if a1 > min_alignment and a2 > min_alignment:
                            score = (a1 + a2) - (math.exp(d_ct * 50) - 1)
                            if score > best_score: best_score = score; best_match = (i, 'cand_tail-seed_head', score, d_ct)

                    # 4. Cand Head-Seed Head
                    if d_ch < max_gap:
                        gap_v = self.get_vector(cand_head, seed_head)
                        a1 = self.calculate_angle_score(v_c_head_out, gap_v) if d_ch > 1e-5 else 1.0
                        a2 = self.calculate_angle_score(gap_v, v_head_in) if d_ch > 1e-5 else 1.0

                        if d_ch < ignore_align_dist: a1=1.0; a2=1.0

                        if a1 > min_alignment and a2 > min_alignment:
                            score = (a1 + a2) - (math.exp(d_ch * 50) - 1)
                            if score > best_score: best_score = score; best_match = (i, 'cand_head-seed_head', score, d_ch)

                if best_match:
                    idx, mtype, score, dist = best_match
                    cand = pool.pop(idx)
                    cand_geom = cand['geometry']

                    if mtype == 'tail-head': seed_geom.extend(cand_geom)
                    elif mtype == 'tail-tail': seed_geom.extend(cand_geom[::-1])
                    elif mtype == 'cand_tail-seed_head': seed_geom[:] = cand_geom + seed_geom
                    elif mtype == 'cand_head-seed_head': seed_geom[:] = cand_geom[::-1] + seed_geom

                    seed['length'] += cand['length']
                    extended = True

            final_paths.append(seed_geom)

        return final_paths

    def clean_line(self, line_name):
        print(f"Cleaning {line_name}...")
        raw_geom = self.get_line_raw_geometry(line_name)
        if not raw_geom:
            print("No raw geometry found.")
            return
        if raw_geom and isinstance(raw_geom[0][0], float): raw_geom = [raw_geom]

        paths = self.cluster_strict(raw_geom, tol=1e-4)
        print(f"  Strict clustering found {len(paths)} components.")

        # Relaxed parameters
        # Yamanote needs 0.06 to catch the 0.0507 gap
        max_gap = 0.03
        if line_name == '山手線':
            max_gap = 0.06

        paths = self.extend_seeds(paths, max_gap=max_gap, min_alignment=0.0)
        print(f"  After extension: {len(paths)} components.")

        final_segments = []
        for i, path in enumerate(paths):
            length = sum(self.distance(path[j], path[j+1]) for j in range(len(path)-1))
            d_loop = self.distance(path[0], path[-1])
            is_loop = False

            if length > 0.1:
                if d_loop < 0.08:
                    is_loop = True
                    if line_name == '山手線' and length > 0.15:
                        path.append(path[0])
                        print(f"  Closed loop for {line_name} (Length {length:.3f})")

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
