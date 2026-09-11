"""Run local RGB-D perception, frozen memory replay and offline search in one command."""

import argparse
import json
from pathlib import Path
import sqlite3
import time

from extract_mapped_rgbd import file_hash
from observe_rgbd_objects import observe
from preview_search_goal import load_grid
from replay_observation_search import replay_search


def run_demo(frames, model, nodes, mapping, label, output, simulated_xy):
    if not nodes or len(set(nodes)) != len(nodes):
        raise ValueError('Select at least one node, each exactly once')
    json.dumps(simulated_xy, allow_nan=False)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'active_stage': 'input_validation',
              'frames_path': str(frames), 'model_path': str(model), 'mapping_path': str(mapping),
              'selected_nodes': nodes, 'query_label': label, 'simulated_start_xy_m': simulated_xy,
              'input_kind': 'saved_rgbd_frames_with_final_map_poses', 'map_frame': 'map', 'coordinate_unit': 'meter',
              'live_capture_executed': False, 'motion_executed': False, 'new_coverage_measured': False,
              'stages': [], 'timeline': [],
              'limitation': 'Offline perception and search on saved frames with final frozen geometry and simulated starts. No live SLAM, physical visibility, object identity or navigation acceptance.'}
    try:
        report.update(frames_sha256=file_hash(frames), model_sha256=file_hash(model))
        manifest = json.loads(frames.read_text())
        grid, occupancy = load_grid(mapping, {'map_frame': 'map', 'point_unit': 'meter',
            'database_sha256': manifest['database_sha256'], 'camera_poses_sha256': manifest['camera_poses_sha256']})
        grid.cell_xy(simulated_xy)
        report['occupancy'] = occupancy
        report['active_stage'] = 'perception'
        report['stages'].append({'name': 'perception', 'report': 'perception/observations.json', 'status': 'INCOMPLETE'})
        code = observe(argparse.Namespace(frames=frames, model=model, nodes=nodes, output=output/'perception'))
        perception = json.loads((output/'perception/observations.json').read_text())
        report['stages'][0].update(status=perception['status'], exit_code=code)
        if (perception['model_sha256'] != report['model_sha256']
                or [f['node_id'] for f in perception['frames']] != nodes
                or any(f['frames_manifest_sha256'] != report['frames_sha256'] for f in perception['frames'])):
            raise ValueError('Perception output differs from the requested source/model identity or node selection')
        report['perception'] = {'accepted_observations': perception['accepted_observations'],
                                'rejected_detections': perception['rejected_detections']}
        if code == 2 and perception['status'] == 'NO_VALID_OBSERVATIONS':
            status = 'NO_VALID_OBSERVATIONS'
            report['reason'] = 'no_depth_accepted_observations'
        elif code == 0 and perception['status'] == 'MEASURED':
            report['active_stage'] = 'replay'
            report['stages'].append({'name': 'replay', 'report': 'replay/replay.json', 'status': 'INCOMPLETE'})
            replay = replay_search(output/'perception/observations.json', mapping, label, output/'replay', simulated_xy)
            if replay['status'] != 'REPLAY_COMPLETE':
                raise RuntimeError('Replay did not complete')
            report['stages'][-1]['status'] = replay['status']
            report['timeline'] = [{key: step[key] for key in
                ('node_id', 'source_stamp_ns', 'query', 'search_status', 'branch', 'branch_reason')}
                for step in replay['steps']]
            status = 'DEMO_COMPLETE'
        else:
            raise RuntimeError('Perception did not return a supported completed outcome')
        report['active_stage'] = 'final_validation'
        if file_hash(frames) != report['frames_sha256'] or file_hash(model) != report['model_sha256']:
            raise ValueError('Source frames manifest or model changed during the demo')
        for stage in report['stages']:
            path = output/stage['report']
            stage.update(sha256=file_hash(path),
                         images=[str(p.relative_to(output)) for p in sorted(path.parent.rglob('*.png'))])
        report.update(status=status, active_stage=None)
    except (ValueError, OSError, KeyError, sqlite3.Error, RuntimeError) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'demo.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('frames', 'model', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--nodes', type=int, nargs='+', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--simulated-start-xy', type=float, nargs=2, required=True, metavar=('X_M', 'Y_M'))
    args = parser.parse_args()
    report = run_demo(args.frames.resolve(), args.model.resolve(), args.nodes, args.mapping.resolve(), args.label,
                      args.output.resolve(), args.simulated_start_xy)
    print(json.dumps({'status': report['status'], 'timeline': report['timeline'],
                      'report': str(args.output.resolve()/'demo.json'), 'duration_ms': report['duration_ms']},
                     indent=2, allow_nan=False))
    raise SystemExit(0 if report['status'] == 'DEMO_COMPLETE' else 2)
