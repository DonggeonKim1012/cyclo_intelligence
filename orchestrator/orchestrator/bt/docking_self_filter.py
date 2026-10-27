"""Nav2 footprint clearing for docking's raw scan collision checks.

Only strictly interior points are removed. The caller must supply a fresh,
time-aligned Nav2 footprint in the same base frame as the scan points.
"""
import numpy as np


def exclude_footprint_interior(points, polygon):
    scan = np.asarray(points, dtype=float).reshape(-1, 2)
    boundary = np.asarray(polygon, dtype=float)
    if (boundary.ndim != 2 or boundary.shape[1] != 2 or len(boundary) < 3
            or not np.isfinite(boundary).all() or not np.isfinite(scan).all()):
        raise ValueError('Invalid self-filter points or footprint')
    if np.allclose(boundary[0], boundary[-1], atol=1e-9, rtol=0):
        boundary = boundary[:-1]
    if len(boundary) < 3:
        raise ValueError('Degenerate self-filter footprint')
    edges = np.roll(boundary, -1, axis=0) - boundary
    lengths = np.linalg.norm(edges, axis=1)
    if np.any(lengths < 1e-8):
        raise ValueError('Degenerate self-filter edge')
    area2 = np.sum(boundary[:, 0] * np.roll(boundary[:, 1], -1)
                   - boundary[:, 1] * np.roll(boundary[:, 0], -1))
    if abs(area2) < 1e-8:
        raise ValueError('Degenerate self-filter area')
    direction = np.sign(area2)
    # Require every vertex to lie on the interior side of every edge. This
    # rejects concave/self-intersecting input rather than widening a blind area.
    def signed_distances(values):
        delta = values[:, None, :] - boundary[None, :, :]
        return direction * (edges[None, :, 0] * delta[:, :, 1]
                            - edges[None, :, 1] * delta[:, :, 0]) / lengths
    if np.any(signed_distances(boundary) < -1e-8):
        raise ValueError('Non-convex self-filter footprint')
    if not np.all(signed_distances(np.zeros((1, 2))) > 1e-6):
        raise ValueError('Self-filter footprint does not enclose base origin')
    # Keep boundary points and all exterior points as possible obstacles.
    interior = np.all(signed_distances(scan) > 1e-6, axis=1)
    return scan[~interior], scan[interior]
