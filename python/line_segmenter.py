import logging
import shapely
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import split, nearest_points, linemerge, unary_union
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
            # Fallback to original
            if isinstance(self.original_geometry, LineString):
                self.original_geometry = MultiLineString([self.original_geometry])

        self.stations = stations
        # Ensure station locations are Shapely Points
        for s in self.stations:
            if not isinstance(s['location'], Point):
                s['location'] = Point(s['location'])

        # We will store the "snapped" location on the line for each station
        self.snapped_stations = {} # name -> Point
        self.station_knives = {}   # name -> LineString (Knife)
        self.debug_knives = []     # For visualization
        self.debug_partial_segments = []

    def _snap_stations_to_geometry(self):
        """
        Projects each station onto the nearest point on the line geometry.
        """
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
        """
        Calculates the tangent vector.
        """
        point = self.snapped_stations[station_name]
        tangents = []

        for geom in self.original_geometry.geoms:
            proj_dist = geom.project(point)
            proj_point = geom.interpolate(proj_dist)

            # If point is effectively on this line segment
            if point.distance(proj_point) < 1e-6:
                d_before = max(0, proj_dist - delta)
                d_after = min(geom.length, proj_dist + delta)

                if d_after - d_before < 1e-9:
                     continue

                p_before = geom.interpolate(d_before)
                p_after = geom.interpolate(d_after)

                dx = p_after.x - p_before.x
                dy = p_after.y - p_before.y

                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    tangents.append((dx/length, dy/length))

        if not tangents:
            # logger.warning(f"No tangent found for {station_name}, defaulting to horizontal.")
            return (1, 0)

        ref = tangents[0]
        sum_dx, sum_dy = 0, 0

        for dx, dy in tangents:
            if dx*ref[0] + dy*ref[1] < 0:
                dx, dy = -dx, -dy
            sum_dx += dx
            sum_dy += dy

        avg_len = math.sqrt(sum_dx**2 + sum_dy**2)
        if avg_len == 0:
            return (1, 0)

        return (sum_dx/avg_len, sum_dy/avg_len)

    def _create_knives(self, knife_length=0.002):
        """
        Generates cut lines (knives) for all stations.
        """
        knives = []
        for s in self.stations:
            name = s['name']
            center = self.snapped_stations[name]
            tx, ty = self._calculate_local_tangent(name)

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

        knives_geom = self._create_knives()

        # Split geometry
        shattered_collection = split(self.original_geometry, knives_geom)
        logger.info(f"Geometry split into {len(shattered_collection.geoms)} parts.")

        segments = {}
        partial_segments = []

        partial_stats = {"StartOnly": 0, "EndOnly": 0, "None": 0}

        for geom in shattered_collection.geoms:
            if geom.is_empty:
                continue

            p_start = Point(geom.coords[0])
            p_end = Point(geom.coords[-1])

            start_station = self._find_station_on_knife(p_start, threshold=1e-4)
            end_station = self._find_station_on_knife(p_end, threshold=1e-4)

            if start_station and end_station and start_station != end_station:
                key = tuple(sorted((start_station, end_station)))
                if key not in segments:
                    segments[key] = []
                segments[key].append(geom)
            else:
                if start_station: partial_stats["StartOnly"] += 1
                elif end_station: partial_stats["EndOnly"] += 1
                else: partial_stats["None"] += 1

                partial_segments.append({
                    "start": start_station,
                    "end": end_station,
                    "geometry": geom
                })

        logger.info(f"Partial Segment Stats: {partial_stats}")
        result = {k: MultiLineString(v) for k, v in segments.items()}

        self.debug_partial_segments = partial_segments

        return result

    def _find_station_on_knife(self, point, threshold=1e-5):
        """
        Checks if the point lies on (or very close to) any station's knife.
        """
        for name, knife in self.station_knives.items():
            # distance from point to line segment
            dist = knife.distance(point)
            if dist < threshold:
                return name
        return None
