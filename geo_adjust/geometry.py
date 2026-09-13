"""Geometric quantities and their partial derivatives w.r.t. point coordinates.

Convention: X = north, Y = east, azimuth measured clockwise from X toward Y.
For two points i (from) and j (to): dX = Xj - Xi, dY = Yj - Yi,
S = sqrt(dX^2 + dY^2), alpha = atan2(dY, dX).
"""

import math


def wrap_angle(a: float) -> float:
    """Wrap an angle (radians) to (-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def distance(xi: float, yi: float, xj: float, yj: float) -> float:
    return math.hypot(xj - xi, yj - yi)


def distance_partials(xi: float, yi: float, xj: float, yj: float):
    """Returns (dS/dXi, dS/dYi, dS/dXj, dS/dYj)."""
    dx = xj - xi
    dy = yj - yi
    s = math.hypot(dx, dy)
    cos_a = dx / s
    sin_a = dy / s
    return (-cos_a, -sin_a, cos_a, sin_a)


def azimuth(xi: float, yi: float, xj: float, yj: float) -> float:
    return math.atan2(yj - yi, xj - xi)


def azimuth_partials(xi: float, yi: float, xj: float, yj: float):
    """Returns (dAlpha/dXi, dAlpha/dYi, dAlpha/dXj, dAlpha/dYj)."""
    dx = xj - xi
    dy = yj - yi
    s2 = dx * dx + dy * dy
    return (dy / s2, -dx / s2, -dy / s2, dx / s2)


def angle(xi: float, yi: float, xj: float, yj: float, xk: float, yk: float) -> float:
    """Horizontal angle at i, turned from ray i->j to ray i->k."""
    a_ij = azimuth(xi, yi, xj, yj)
    a_ik = azimuth(xi, yi, xk, yk)
    return wrap_angle(a_ik - a_ij)


def angle_partials(xi: float, yi: float, xj: float, yj: float, xk: float, yk: float):
    """Returns partials of angle w.r.t. (Xi, Yi, Xj, Yj, Xk, Yk)."""
    dij_i_x, dij_i_y, dij_j_x, dij_j_y = azimuth_partials(xi, yi, xj, yj)
    dik_i_x, dik_i_y, dik_k_x, dik_k_y = azimuth_partials(xi, yi, xk, yk)

    d_xi = dik_i_x - dij_i_x
    d_yi = dik_i_y - dij_i_y
    d_xj = -dij_j_x
    d_yj = -dij_j_y
    d_xk = dik_k_x
    d_yk = dik_k_y
    return (d_xi, d_yi, d_xj, d_yj, d_xk, d_yk)
