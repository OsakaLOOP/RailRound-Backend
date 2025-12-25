import logging
import shapely
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import split, nearest_points, linemerge, unary_union, snap
import numpy as np
import math

logger = logging.getLogger(__name__)

class LineSegmenter:
    def __init__(self, line_geometry, stations):
        """
        :param line_geometry: Shapely MultiLineString or LineString
        :param stations: List of station objects/dicts.
                         Must have 'location' (Point) and 'name' (str).
        """
        self.original_geometry = line_geometry

        # Merge the geometry first to fix fragmentation
        try:
            merged = linemerge(self.original_geometry)
            if isinstance(merged, LineString):
                self.original_geometry = MultiLineString([merged])
            else:
                self.original_geometry = merged
            logger.info(f"Geometry merged. Now has {len(self.original_geometry.geoms)} continuous lines.")
        except Exception as e:
            logger.error(f"Error during linemerge: {e}")
            if isinstance(self.original_geometry, LineString):
                self.original_geometry = MultiLineString([self.original_geometry])

        self.stations = stations
        for s in self.stations:
            if not isinstance(s['location'], Point):
                s['location'] = Point(s['location'])

        self.snapped_stations = {} # name -> Point
        self.station_knives = {}   # name -> LineString (Knife)
        self.debug_knives = []
        self.debug_partial_segments = []
        self.segments = {}         # The resulting graph (StationA, StationB) -> MultiLineString

        # Cache for loose connections
        self.loose_connections = []

    def _snap_stations_to_geometry(self):
        for s in self.stations:
            best_dist = float('inf')
            best_point = None
            for geom in self.original_geometry.geoms:
                proj_dist = geom.project(s['location'])
                proj_point = geom.interpolate(proj_dist)
                dist = s['location'].distance(proj_point)
                if dist < best_dist:
                    best_dist = dist
                    best_point = proj_point
            self.snapped_stations[s['name']] = best_point

    def _calculate_local_tangent(self, station_name, delta=0.0005):
        point = self.snapped_stations[station_name]
        tangents = []
        for geom in self.original_geometry.geoms:
            proj_dist = geom.project(point)
            proj_point = geom.interpolate(proj_dist)
            if point.distance(proj_point) < 1e-6:
                d_before = max(0, proj_dist - delta)
                d_after = min(geom.length, proj_dist + delta)
                if d_after - d_before < 1e-9: continue
                p_before = geom.interpolate(d_before)
                p_after = geom.interpolate(d_after)
                dx = p_after.x - p_before.x
                dy = p_after.y - p_before.y
                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    tangents.append((dx/length, dy/length))

        if not tangents: return (1, 0)
        ref = tangents[0]
        sum_dx, sum_dy = 0, 0
        for dx, dy in tangents:
            if dx*ref[0] + dy*ref[1] < 0: dx, dy = -dx, -dy
            sum_dx += dx
            sum_dy += dy
        avg_len = math.sqrt(sum_dx**2 + sum_dy**2)
        if avg_len == 0: return (1, 0)
        return (sum_dx/avg_len, sum_dy/avg_len)

    def _create_knives(self, knife_length=0.002, mode='tangent', connectivity=None):
        """
        Generates cut lines (knives).
        mode: 'tangent' (default) or 'neighbor' (uses connectivity graph).
        """
        knives = []
        for s in self.stations:
            name = s['name']
            center = self.snapped_stations[name]

            tx, ty = 0, 0

            if mode == 'neighbor' and connectivity:
                # Find neighbors for this station
                neighbors = []
                for (a, b) in connectivity.keys():
                    if a == name: neighbors.append(b)
                    if b == name: neighbors.append(a)

                if neighbors:
                    # Calculate vector to average neighbor position
                    avg_nx, avg_ny = 0, 0
                    valid_neighbors = 0
                    for n_name in neighbors:
                        if n_name in self.snapped_stations:
                            n_pt = self.snapped_stations[n_name]
                            dx = n_pt.x - center.x
                            dy = n_pt.y - center.y
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                avg_nx += dx/length
                                avg_ny += dy/length
                                valid_neighbors += 1

                    if valid_neighbors > 0:
                        tx, ty = avg_nx/valid_neighbors, avg_ny/valid_neighbors
                    else:
                        tx, ty = self._calculate_local_tangent(name)
                else:
                    tx, ty = self._calculate_local_tangent(name)
            else:
                tx, ty = self._calculate_local_tangent(name)

            # Normalize
            l = math.sqrt(tx*tx + ty*ty)
            if l == 0: tx, ty = 1, 0
            else: tx, ty = tx/l, ty/l

            # Knife direction is perpendicular (-ty, tx)
            kx, ky = -ty, tx

            p1 = Point(center.x + kx * knife_length, center.y + ky * knife_length)
            p2 = Point(center.x - kx * knife_length, center.y - ky * knife_length)

            knife = LineString([p1, p2])
            knives.append(knife)
            self.station_knives[name] = knife

        self.debug_knives = knives
        return MultiLineString(knives)

    def segment(self):
        self._snap_stations_to_geometry()

        # --- PASS 1: Local Tangent ---
        logger.info("Starting Pass 1: Local Tangent Knives")
        knives_geom_1 = self._create_knives(mode='tangent')
        self._perform_cut(knives_geom_1)
        self.seal_paths(gap_tolerance=1e-4)

        preliminary_connectivity = self.segments.copy()
        logger.info(f"Pass 1 found {len(preliminary_connectivity)} segments.")

        # --- PASS 2: Neighbor Facing ---
        logger.info("Starting Pass 2: Neighbor Facing Knives")
        # Use the preliminary graph to orient knives
        knives_geom_2 = self._create_knives(mode='neighbor', connectivity=preliminary_connectivity)
        self._perform_cut(knives_geom_2)

        # Use LOOSER sealing in Pass 2
        self.seal_paths(gap_tolerance=5e-4) # 5x tolerance (~50m)

        logger.info(f"Pass 2 found {len(self.segments)} segments.")
        result = {k: MultiLineString(v) for k, v in self.segments.items()}
        return result

    def _perform_cut(self, knives_geom):
        shattered_collection = split(self.original_geometry, knives_geom)

        self.segments = {}
        partial_segments = []
        partial_stats = {"StartOnly": 0, "EndOnly": 0, "None": 0}

        for geom in shattered_collection.geoms:
            if geom.is_empty: continue
            p_start = Point(geom.coords[0])
            p_end = Point(geom.coords[-1])
            start_station = self._find_station_on_knife(p_start, threshold=1e-4)
            end_station = self._find_station_on_knife(p_end, threshold=1e-4)

            if start_station and end_station and start_station != end_station:
                key = tuple(sorted((start_station, end_station)))
                if key not in self.segments: self.segments[key] = []
                self.segments[key].append(geom)
            else:
                if start_station: partial_stats["StartOnly"] += 1
                elif end_station: partial_stats["EndOnly"] += 1
                else: partial_stats["None"] += 1
                partial_segments.append({"start": start_station, "end": end_station, "geometry": geom})

        self.debug_partial_segments = partial_segments
        logger.info(f"Partial Segment Stats: {partial_stats}")

    def _find_station_on_knife(self, point, threshold=1e-5):
        for name, knife in self.station_knives.items():
            if knife.distance(point) < threshold: return name
        return None

    def seal_paths(self, gap_tolerance=1e-4):
        """
        Attempts to close gaps between segments.
        """
        starts = [p for p in self.debug_partial_segments if p['start'] and not p['end']]
        ends = [p for p in self.debug_partial_segments if not p['start'] and p['end']]

        sealed_count = 0

        for s_seg in starts:
            p1 = Point(s_seg['geometry'].coords[-1])
            best_match = None
            best_dist = gap_tolerance

            for e_seg in ends:
                p2 = Point(e_seg['geometry'].coords[0])
                dist = p1.distance(p2)
                if dist < best_dist:
                    best_dist = dist
                    best_match = e_seg

            if best_match:
                start_st = s_seg['start']
                end_st = best_match['end']

                # Merge geometries
                coords1 = list(s_seg['geometry'].coords)
                coords2 = list(best_match['geometry'].coords)
                new_geom = LineString(coords1 + coords2)

                key = tuple(sorted((start_st, end_st)))
                if key not in self.segments: self.segments[key] = []
                self.segments[key].append(new_geom)

                sealed_count += 1

                # Cache loose connection info
                self.loose_connections.append({
                    "u": start_st, "v": end_st, "gap": best_dist
                })

        logger.info(f"Sealed {sealed_count} gaps (tol={gap_tolerance}).")
