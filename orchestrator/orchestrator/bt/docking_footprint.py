"""SG2 Autonomy Studio base outline, base_link metres; not an arm envelope."""
import math
import numpy as np

SG2_BASE_OUTLINE = [[-0.4029, -0.0522], [-0.3774, -0.1649], [-0.3626, -0.209], [-0.3241, -0.2352], [-0.0819, -0.301], [0.1516, -0.301], [0.1795, -0.2954], [0.2032, -0.2796], [0.219, -0.2559], [0.2246, -0.228], [0.2246, 0.228], [0.219, 0.2559], [0.2032, 0.2796], [0.1795, 0.2954], [0.1516, 0.301], [-0.0819, 0.301], [-0.3241, 0.2352], [-0.3626, 0.209], [-0.3774, 0.1649]]

# Convex envelope includes wheel corners protruding beyond the shell.
SG2_BASE_FOOTPRINT = [(-0.4029, -0.0522), (-0.3774, -0.1649), (-0.3626, -0.209), (-0.3241, -0.2352), (-0.0819, -0.301), (0.1516, -0.301), (0.1795, -0.2954), (0.2236, -0.28040000000000004), (0.2246, -0.228), (0.2246, 0.228), (0.2236, 0.28040000000000004), (0.1795, 0.2954), (0.1516, 0.301), (-0.0819, 0.301), (-0.3241, 0.2352), (-0.3626, 0.209), (-0.3774, 0.1649)]


def exclude_receding_rear_clearance(points, command, clearance=.01, horizon=.5):
    """Ignore rear-edge returns only when the commanded motion separates from them.

    The SG2 outline is approximate. A return a few millimetres outside its rear
    edge may be part of the robot or a real object already next to it. Neither
    case should prevent a provably receding forward command; both must still
    block motion toward the return. The angular bound certifies separation for
    the whole horizon, including the intervals between collision samples.
    """
    scan = np.asarray(points, dtype=float).reshape(-1, 2)
    vx, vy, wz = map(float, command)
    if not np.isfinite(scan).all() or not all(math.isfinite(v) for v in (vx, vy, wz)):
        raise ValueError('Non-finite scan point or base command')
    if not len(scan) or vx <= 0:
        return scan, scan[:0]

    polygon = np.asarray(SG2_BASE_FOOTPRINT)
    # This is the back edge of the Studio outline. Restrict the exemption to
    # points whose perpendicular projection lies on the edge itself.
    start, end = polygon[-1], polygon[0]
    edge = end - start
    length = np.linalg.norm(edge)
    inward = np.array([-edge[1], edge[0]]) / length
    offsets = scan - start
    along = offsets @ edge / (length * length)
    signed = offsets @ inward
    speed = math.hypot(vx, vy)
    # The swept guard adds at most 2.5 mm between samples spaced <= 5 mm.
    near_edge = ((along >= 0) & (along <= 1) & (signed < -1e-6)
                 & (signed >= -(clearance + .0025)))
    # For a stationary point in the moving base frame,
    # d(signed)/dt = -inward·velocity - wz*inward·J(point).
    # |point(t)| <= |point(0)| + speed*horizon, so this strict bound means its
    # distance outside the rear supporting line increases at every instant.
    separating = (inward @ np.array([vx, vy])
                  > abs(wz) * (np.linalg.norm(scan, axis=1) + speed * horizon) + 1e-3)
    ignored = near_edge & separating
    return scan[~ignored], scan[ignored]

def swept_obstacle(points, command, clearance=.01, horizon=.5):
    vx, vy, wz = map(float, command)
    if not all(math.isfinite(v) for v in (vx, vy, wz)):
        raise ValueError('Non-finite base command')
    if math.hypot(vx, vy) < 1e-5 and abs(wz) < 1e-5:
        return None
    scan = np.asarray(points, dtype=float).reshape(-1, 2)
    if not np.isfinite(scan).all(): raise ValueError('Non-finite scan point')
    if not len(scan): return None
    polygon = np.asarray(SG2_BASE_FOOTPRINT)
    radius = float(np.linalg.norm(polygon, axis=1).max())
    travel = (math.hypot(vx, vy) + abs(wz)*radius)*horizon
    steps = max(1, math.ceil(travel/.005))
    padding = clearance + travel/steps/2
    edges = np.roll(polygon, -1, axis=0)-polygon
    lengths = np.linalg.norm(edges, axis=1)
    for t in np.linspace(0., horizon, steps+1):
        a = wz*t; c, s = math.cos(a), math.sin(a)
        if abs(wz) > 1e-8:
            x = (vx*s + vy*(c-1))/wz
            y = (vx*(1-c) + vy*s)/wz
        else: x, y = vx*t, vy*t
        local = (scan-[x,y]) @ np.array([[c,-s],[s,c]])
        inside = np.ones(len(scan), dtype=bool)
        for start, edge, length in zip(polygon, edges, lengths):
            delta = local-start
            inside &= (edge[0]*delta[:,1]-edge[1]*delta[:,0]) >= -padding*length
        found = np.flatnonzero(inside)
        if len(found):
            return {'point_base_m':scan[found[0]].tolist(), 'lookahead_s':float(t),
                    'command':list(command), 'clearance_m':clearance,
                    'footprint':'sg2_autonomy_base'}
    return None
