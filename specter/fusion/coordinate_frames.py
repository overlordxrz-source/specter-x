"""Rigid transforms (R, t) between sensor frames and pinhole projection.

Conventions
-----------
* A Transform T_a_b maps points expressed in frame b into frame a:
      p_a = R @ p_b + t
* Camera frames follow the OpenCV convention: +x right, +y down, +z forward.
* Body frame ("body") is the device: +x forward, +y left, +z up (ROS REP-103).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np


def rot_x(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def rot_y(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)


def rot_z(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Z-Y-X intrinsic (yaw, then pitch, then roll), radians."""
    return rot_z(yaw) @ rot_y(pitch) @ rot_x(roll)


def quat_to_matrix(w: float, x: float, y: float, z: float) -> np.ndarray:
    """Unit quaternion (w, x, y, z) -> rotation matrix (BNO085 reports this form)."""
    q = np.array([w, x, y, z], dtype=float)
    n = np.linalg.norm(q)
    if n == 0:
        raise ValueError("zero quaternion")
    w, x, y, z = q / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


# Body (x fwd, y left, z up) -> camera optical (x right, y down, z fwd)
R_CAM_BODY = np.array([[0, -1, 0], [0, 0, -1], [1, 0, 0]], dtype=float)


@dataclass
class Transform:
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self) -> None:
        self.R = np.asarray(self.R, dtype=float).reshape(3, 3)
        self.t = np.asarray(self.t, dtype=float).reshape(3)
        if not np.allclose(self.R @ self.R.T, np.eye(3), atol=1e-6):
            raise ValueError("R is not orthonormal")
        if not np.isclose(np.linalg.det(self.R), 1.0, atol=1e-6):
            raise ValueError("R must be a proper rotation (det=+1)")

    @classmethod
    def identity(cls) -> "Transform":
        return cls()

    def apply(self, points: np.ndarray) -> np.ndarray:
        """Transform (3,) or (N,3) points."""
        p = np.asarray(points, dtype=float)
        return p @ self.R.T + self.t

    def inverse(self) -> "Transform":
        Rt = self.R.T
        return Transform(Rt, -Rt @ self.t)

    def __matmul__(self, other: "Transform") -> "Transform":
        """Compose: (T_a_b @ T_b_c) = T_a_c."""
        return Transform(self.R @ other.R, self.R @ other.t + self.t)

    def as_matrix(self) -> np.ndarray:
        M = np.eye(4)
        M[:3, :3] = self.R
        M[:3, 3] = self.t
        return M

    @classmethod
    def from_matrix(cls, M: np.ndarray) -> "Transform":
        M = np.asarray(M, dtype=float)
        return cls(M[:3, :3], M[:3, 3])

    def to_dict(self) -> dict:
        return {"R": self.R.tolist(), "t": self.t.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "Transform":
        return cls(d["R"], d["t"])


@dataclass
class PinholeCamera:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    dist: Optional[np.ndarray] = None   # OpenCV k1,k2,p1,p2,k3 (ignored by project())

    @classmethod
    def from_fov(cls, width: int, height: int, hfov_deg: float) -> "PinholeCamera":
        fx = (width / 2) / np.tan(np.radians(hfov_deg) / 2)
        return cls(fx, fx, width / 2, height / 2, width, height)

    @property
    def K(self) -> np.ndarray:
        return np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1.0]])

    def project(self, points_cam: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Project camera-frame points (N,3) to pixels (N,2).

        Returns (uv, valid) where valid is False for points behind the camera
        (z <= 0) or outside the image. uv is NaN where z <= 0.
        """
        p = np.atleast_2d(np.asarray(points_cam, dtype=float))
        z = p[:, 2]
        uv = np.full((p.shape[0], 2), np.nan)
        front = z > 1e-9
        uv[front, 0] = self.fx * p[front, 0] / z[front] + self.cx
        uv[front, 1] = self.fy * p[front, 1] / z[front] + self.cy
        inside = (
            front
            & (uv[:, 0] >= 0) & (uv[:, 0] < self.width)
            & (uv[:, 1] >= 0) & (uv[:, 1] < self.height)
        )
        return uv, inside

    def unproject(self, uv: np.ndarray, depth: np.ndarray) -> np.ndarray:
        """Pixels (N,2) + depth along +z (N,) -> camera-frame points (N,3)."""
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        d = np.asarray(depth, dtype=float).reshape(-1)
        x = (uv[:, 0] - self.cx) / self.fx * d
        y = (uv[:, 1] - self.cy) / self.fy * d
        return np.stack([x, y, d], axis=1)

    def bearing(self, uv: np.ndarray) -> np.ndarray:
        """Unit ray directions in camera frame for pixels (N,2)."""
        rays = self.unproject(uv, np.ones(np.atleast_2d(uv).shape[0]))
        return rays / np.linalg.norm(rays, axis=1, keepdims=True)


class FrameGraph:
    """Tiny registry of static extrinsics: T_parent_child edges, resolved by chaining."""

    def __init__(self) -> None:
        self._edges: Dict[Tuple[str, str], Transform] = {}

    def add(self, parent: str, child: str, T_parent_child: Transform) -> None:
        self._edges[(parent, child)] = T_parent_child
        self._edges[(child, parent)] = T_parent_child.inverse()

    def lookup(self, target: str, source: str) -> Transform:
        """Return T_target_source (BFS over edges)."""
        if target == source:
            return Transform.identity()
        from collections import deque

        q = deque([(source, Transform.identity())])  # T_node_source
        seen = {source}
        while q:
            node, T_node_src = q.popleft()
            for (a, b), T_a_b in self._edges.items():
                if b == node and a not in seen:
                    T_a_src = T_a_b @ T_node_src
                    if a == target:
                        return T_a_src
                    seen.add(a)
                    q.append((a, T_a_src))
        raise KeyError(f"no transform path {source} -> {target}")


def project_points(points_world: np.ndarray, T_cam_world: Transform, cam: PinholeCamera):
    """Convenience: world points -> pixels via extrinsics + intrinsics."""
    return cam.project(T_cam_world.apply(points_world))
