"""Shared rectified-camera intrinsics and frozen map-from-camera pose checks."""

import numpy as np
from scipy.spatial.transform import Rotation


def pinhole_matrix(k):
    k = np.asarray(k, dtype=float).reshape(3, 3)
    if (not np.isfinite(k).all() or k[0, 0] <= 0 or k[1, 1] <= 0
            or not np.array_equal(k[2], [0, 0, 1]) or k[0, 1] or k[1, 0]):
        raise ValueError('Invalid pinhole intrinsics')
    return k


def map_from_camera(position, quaternion):
    values = np.r_[position, quaternion]
    if (np.shape(position) != (3,) or np.shape(quaternion) != (4,)
            or not np.isfinite(values).all()
            or not np.isclose(np.linalg.norm(quaternion), 1, atol=2e-6, rtol=0)):
        raise ValueError('Expected finite translation and normalized camera quaternion')
    transform = np.eye(4)
    transform[:3, :3] = Rotation.from_quat(quaternion).as_matrix()
    transform[:3, 3] = position
    return transform
