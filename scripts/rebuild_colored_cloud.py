"""Fuse verified mapped RGB-D frames and write a self-contained, rotatable map."""

import argparse
import json
from pathlib import Path
import time

import numpy as np
import open3d as o3d
import plotly.graph_objects as go
from scipy.spatial.transform import Rotation

from extract_mapped_rgbd import file_hash


def project_frame(rgb, depth_mm, k, position, quaternion, stride=2, max_depth_m=5.0):
    """Back-project optical x-right/y-down/z-forward, then apply map-from-camera."""
    k = np.asarray(k, dtype=float).reshape(3, 3)
    pose_values = np.r_[position, quaternion]
    if (rgb.dtype != np.uint8 or depth_mm.dtype != np.uint16
            or rgb.shape != (*depth_mm.shape, 3) or depth_mm.ndim != 2):
        raise ValueError('Expected same-grid RGB8 and raw uint16 millimeter depth')
    if (not np.isfinite(k).all() or k[0, 0] <= 0 or k[1, 1] <= 0
            or not np.array_equal(k[2], [0, 0, 1]) or k[0, 1] or k[1, 0]):
        raise ValueError('Invalid pinhole intrinsics')
    if (pose_values.shape != (7,) or not np.isfinite(pose_values).all()
            or not np.isclose(np.linalg.norm(quaternion), 1, atol=2e-6, rtol=0)):
        raise ValueError('Expected finite translation and normalized camera quaternion')
    if stride < 1 or not np.isfinite(max_depth_m) or max_depth_m <= 0:
        raise ValueError('Invalid sampling stride or depth limit')
    # Sampling preserves the original integer pixel origin; no image resizing.
    color = o3d.geometry.Image(np.ascontiguousarray(rgb[::stride, ::stride]))
    depth = o3d.geometry.Image(np.ascontiguousarray(depth_mm[::stride, ::stride]))
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        color, depth, depth_scale=1000.0, depth_trunc=max_depth_m,
        convert_rgb_to_intensity=False)
    height, width = np.asarray(depth).shape
    intrinsic = o3d.camera.PinholeCameraIntrinsic(
        width, height, k[0, 0]/stride, k[1, 1]/stride, k[0, 2]/stride, k[1, 2]/stride)
    cloud = o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, intrinsic)
    if not len(cloud.points):
        raise ValueError('Frame has no valid depth within the selected range')
    transform = np.eye(4)
    transform[:3, :3] = Rotation.from_quat(quaternion).as_matrix()
    transform[:3, 3] = position
    cloud.transform(transform)
    return cloud


def write_viewer(cloud, frames, path):
    xyz = np.asarray(cloud.points)
    colors = np.rint(np.asarray(cloud.colors)*255).astype(np.uint8)
    # Bound browser work while retaining the complete cloud in the PLY artifact.
    indices = np.linspace(0, len(xyz)-1, min(len(xyz), 180_000), dtype=int)
    traces = [go.Scatter3d(x=xyz[indices, 0], y=xyz[indices, 1], z=xyz[indices, 2],
                          mode='markers', name='RGB-D map', hoverinfo='skip',
                          marker={'size': 1.5, 'color': [f'rgb({r},{g},{b})' for r, g, b in colors[indices]],
                                  'opacity': 1})]
    positions = np.array([row['position_m'] for row in frames])
    traces.append(go.Scatter3d(x=positions[:, 0], y=positions[:, 1], z=positions[:, 2],
                              mode='markers', name='Camera nodes',
                              text=[f'Node {row["node_id"]}' for row in frames], hoverinfo='text',
                              marker={'size': 4, 'color': '#ffbb55'}))
    figure = go.Figure(traces)
    figure.update_layout(
        title=f'Colored point-cloud map | {len(xyz):,} points ({len(indices):,} displayed)<br><sup>Drag to rotate · scroll to zoom · partial coverage; pose accuracy unverified</sup>',
        template='plotly_dark', margin={'l': 0, 'r': 0, 'b': 0, 't': 75},
        scene={'aspectmode': 'data', 'xaxis_title': 'map x (m)', 'yaxis_title': 'map y (m)',
               'zaxis_title': 'map z (m)', 'dragmode': 'orbit',
               'camera': {'eye': {'x': -1.4, 'y': -1.7, 'z': 1.0}}},
        legend={'x': 0.01, 'y': 0.95})
    figure.write_html(path, include_plotlyjs=True, full_html=True,
                      config={'scrollZoom': True, 'displaylogo': False, 'responsive': True},
                      div_id='room-cloud')
    return len(indices)


def rebuild(frames_path, output, voxel_m, stride, max_depth_m):
    manifest = json.loads(frames_path.read_text())
    if manifest['status'] != 'VERIFIED' or manifest['depth_unit'] != 'millimeter':
        raise ValueError('Use verified extracted RGB-D frames')
    if not np.isfinite(voxel_m) or voxel_m <= 0:
        raise ValueError('Voxel size must be finite and positive')
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'INCOMPLETE', 'database_sha256': manifest['database_sha256'],
              'frames_manifest_sha256': file_hash(frames_path), 'frame_count': len(manifest['frames']),
              'pose_provenance': manifest['pose_provenance'], 'coordinate_frame': 'map',
              'coordinate_unit': 'meter', 'voxel_m': voxel_m, 'pixel_stride': stride,
              'max_depth_m': max_depth_m, 'open3d_version': o3d.__version__, 'frames': [],
              'limitation': 'Fixed existing poses; no ICP, new trajectory estimation, hole filling or accuracy improvement claim.'}
    started = time.monotonic()
    cloud = o3d.geometry.PointCloud()
    try:
        for row in manifest['frames']:
            path = frames_path.parent/row['file']
            if file_hash(path) != row['file_sha256']:
                raise ValueError(f'Extracted frame changed: {path}')
            begin = time.monotonic()
            with np.load(path, allow_pickle=False) as frame:
                part = project_frame(frame['rgb'], frame['depth_mm'], manifest['camera_info']['k'],
                                     row['position_m'], row['quaternion_xyzw'], stride, max_depth_m)
            cloud += part
            result['frames'].append({'node_id': row['node_id'], 'points': len(part.points),
                                      'projection_s': time.monotonic()-begin})
            print(f'Projected node {row["node_id"]}: {len(part.points)} points', flush=True)
        result['projected_points'] = len(cloud.points)
        begin = time.monotonic()
        cloud = cloud.voxel_down_sample(voxel_m)
        result['voxel_fusion_s'] = time.monotonic()-begin
        xyz, colors = np.asarray(cloud.points), np.asarray(cloud.colors)
        if not len(xyz) or not np.isfinite(xyz).all() or not np.isfinite(colors).all():
            raise ValueError('Empty or non-finite fused geometry/color')
        ply = output/'room_colored.ply'
        if not o3d.io.write_point_cloud(str(ply), cloud):
            raise RuntimeError('PLY writer failed')
        loaded = o3d.io.read_point_cloud(str(ply))
        if (not np.array_equal(np.asarray(loaded.points), xyz)
                or not np.allclose(np.asarray(loaded.colors), colors, atol=0.5/255+1e-12, rtol=0)):
            raise ValueError('PLY readback changed geometry or exceeded 8-bit color precision')
        displayed = write_viewer(loaded, manifest['frames'], output/'room_colored.html')
        result.update(status='VERIFIED', fused_points=len(xyz), viewer_points=displayed,
                      xyz_min_m=xyz.min(axis=0).tolist(), xyz_max_m=xyz.max(axis=0).tolist(),
                      non_gray_fraction=float(np.mean(np.ptp(np.rint(colors*255), axis=1) > 0)),
                      ply_bytes=ply.stat().st_size, ply_sha256=file_hash(ply), ply_roundtrip_passed=True,
                      html_bytes=(output/'room_colored.html').stat().st_size)
    finally:
        result['duration_s'] = time.monotonic()-started
        (output/'reconstruction.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'frames'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--voxel-m', type=float, default=0.02)
    parser.add_argument('--stride', type=int, default=2)
    parser.add_argument('--max-depth-m', type=float, default=5.0)
    args = parser.parse_args()
    rebuild(args.frames.resolve(), args.output.resolve(), args.voxel_m, args.stride, args.max_depth_m)
