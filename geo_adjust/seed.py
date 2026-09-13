"""Auto-compute approximate coordinates for undetermined points.

This mirrors what a surveyor does by hand ("предвычисление координат"):
starting from a point with known coordinates and a backsight/azimuth for
orientation, propagate coordinates forward along the chain of measurements
via the direct geodetic problem. It walks the observation graph rather than
asking the caller to guess starting coordinates.

A single reference point with no azimuth/direction observation anywhere
leaves the network's rotation undetermined (its shape and scale are still
fully fixed by distances/angles) — handled by assigning one arbitrary
bearing, the same convention a surveyor uses by hand in that situation.

Deliberately out of scope: pure intersection/resection, where a point is
tied only by angles/directions from two or more stations with no direct
chain reaching it. That needs different math (ray/circle intersection, with
a two-solution ambiguity) and is not attempted here — such points are
reported as unresolved rather than guessed at.
"""

import math
from typing import Dict, List, Tuple

from . import geometry as geo
from .model import Observation, Point

Coords = Dict[str, Tuple[float, float]]


def compute_initial_coordinates(
    fixed_points: List[Point],
    observations: List[Observation],
) -> Tuple[Coords, List[str]]:
    """Returns (coords_for_every_resolvable_point, ids_that_could_not_be_resolved).

    `coords` includes the fixed points themselves (unchanged) plus every
    other point reachable from them through the observation graph.
    """
    coords: Coords = {p.id: (p.x, p.y) for p in fixed_points}
    resolved_azimuth: Dict[Tuple[str, str], float] = {}
    station_z: Dict[str, float] = {}

    if not coords and observations:
        # Free network with no reference point at all: seed one arbitrary
        # internal anchor. Its absolute placement is meaningless (as with
        # any free network), only the resulting shape matters, and that is
        # unaffected by this choice.
        coords[observations[0].from_id] = (0.0, 0.0)

    def set_azimuth(i: str, j: str, az: float) -> bool:
        changed = False
        if (i, j) not in resolved_azimuth:
            resolved_azimuth[(i, j)] = az
            changed = True
        if (j, i) not in resolved_azimuth:
            resolved_azimuth[(j, i)] = geo.wrap_angle(az + math.pi)
            changed = True
        return changed

    def set_coords(pid: str, x: float, y: float) -> bool:
        if pid in coords:
            return False
        coords[pid] = (x, y)
        return True

    def try_resolve_from_coords(i: str, j: str) -> bool:
        if i in coords and j in coords and (i, j) not in resolved_azimuth:
            xi, yi = coords[i]
            xj, yj = coords[j]
            return set_azimuth(i, j, geo.azimuth(xi, yi, xj, yj))
        return False

    max_passes = len(observations) + len(fixed_points) + 10

    def propagate() -> None:
        for _ in range(max_passes):
            changed = False

            for obs in observations:
                if try_resolve_from_coords(obs.from_id, obs.to_id):
                    changed = True
                if obs.to_id2 is not None and try_resolve_from_coords(obs.from_id, obs.to_id2):
                    changed = True

                if obs.type == "azimuth":
                    if set_azimuth(obs.from_id, obs.to_id, obs.value):
                        changed = True

                elif obs.type == "distance":
                    i, j = obs.from_id, obs.to_id
                    if (i, j) in resolved_azimuth and i in coords and j not in coords:
                        xi, yi = coords[i]
                        az = resolved_azimuth[(i, j)]
                        if set_coords(j, xi + obs.value * math.cos(az), yi + obs.value * math.sin(az)):
                            changed = True
                    elif (j, i) in resolved_azimuth and j in coords and i not in coords:
                        xj, yj = coords[j]
                        az = resolved_azimuth[(j, i)]
                        if set_coords(i, xj + obs.value * math.cos(az), yj + obs.value * math.sin(az)):
                            changed = True

                elif obs.type == "angle":
                    i, j, k = obs.from_id, obs.to_id, obs.to_id2
                    if (i, j) in resolved_azimuth and (i, k) not in resolved_azimuth:
                        if set_azimuth(i, k, geo.wrap_angle(resolved_azimuth[(i, j)] + obs.value)):
                            changed = True
                    elif (i, k) in resolved_azimuth and (i, j) not in resolved_azimuth:
                        if set_azimuth(i, j, geo.wrap_angle(resolved_azimuth[(i, k)] - obs.value)):
                            changed = True

                elif obs.type == "direction":
                    i, j = obs.from_id, obs.to_id
                    if i in station_z:
                        if set_azimuth(i, j, geo.wrap_angle(obs.value + station_z[i])):
                            changed = True
                    elif (i, j) in resolved_azimuth:
                        station_z[i] = geo.wrap_angle(resolved_azimuth[(i, j)] - obs.value)
                        changed = True

            if not changed:
                break

    def unresolved_ids() -> List[str]:
        all_ids = set(coords)
        for obs in observations:
            all_ids.add(obs.from_id)
            all_ids.add(obs.to_id)
            if obs.to_id2 is not None:
                all_ids.add(obs.to_id2)
        return sorted(pid for pid in all_ids if pid not in coords)

    propagate()

    # A single reference point with only distance/angle observations (no
    # azimuth or direction anywhere) leaves rotation genuinely undetermined:
    # there is no ray anywhere to turn from, so propagation stalls
    # immediately even though the network's shape and scale are fully
    # determined. Surveyors handle exactly this by convention — assign an
    # arbitrary ("условный") bearing to one line purely to have a coordinate
    # system to compute in, exactly like the fully-free-network anchor
    # above. This is only done once, and only when there is *no* real
    # absolute bearing anywhere in the data (`resolved_azimuth` empty): if
    # even one real azimuth/direction exists, any points still unresolved
    # need resection/multilateration instead, which is a different problem
    # and must stay reported as unresolved rather than papered over.
    if unresolved_ids() and coords and not resolved_azimuth:
        for obs in observations:
            if obs.from_id in coords and (obs.from_id, obs.to_id) not in resolved_azimuth:
                set_azimuth(obs.from_id, obs.to_id, 0.0)
                propagate()
                break

    return coords, unresolved_ids()
