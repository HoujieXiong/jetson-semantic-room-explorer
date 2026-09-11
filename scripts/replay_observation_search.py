"""Replay saved observations into frozen memory prefixes and inspect each search decision."""

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import time

from extract_mapped_rgbd import file_hash
from preview_search_goal import load_grid
from run_offline_search import run_search
from scene_memory import import_report, validate_report


def replay_search(observations, mapping, label, output, simulated_xy):
    json.dumps(simulated_xy, allow_nan=False)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'active_stage': 'source_validation', 'active_node': None,
              'observations_path': str(observations), 'mapping_path': str(mapping), 'query_label': label,
              'simulated_start_xy_m': simulated_xy, 'map_frame': 'map', 'coordinate_unit': 'meter',
              'observation_executed': False, 'motion_executed': False, 'new_coverage_measured': False,
              'steps': [],
              'limitation': 'Chronological saved-evidence replay with final frozen occupancy and optimized poses. Observations were not acquired at proposed goals; this is not causal online mapping or physical search acceptance.'}
    try:
        source_hash = file_hash(observations)
        source = json.loads(observations.read_text())
        context, frames = validate_report(source)
        grid, occupancy = load_grid(mapping, context)
        grid.cell_xy(simulated_xy)
        report.update(observations_sha256=source_hash, occupancy=occupancy)
        prefix = {**source, 'frames': [], 'accepted_observations': 0, 'rejected_detections': 0}
        previous = None
        for frame in frames:
            begin = time.monotonic()
            folder = output/f'node_{frame["node_id"]}'
            step = {'status': 'INCOMPLETE', 'node_id': frame['node_id'], 'source_stamp_ns': frame['source_stamp_ns'],
                    'memory': str((folder/'memory.db').relative_to(output)),
                    'search_report': str((folder/'search/search.json').relative_to(output)),
                    'query_observations': [{'detection_index': d['detection_index'], 'depth_status': d['depth']['status'],
                                            'reason': d['depth'].get('reason')}
                                           for d in frame['detections'] if d['label'].strip().casefold() == label.strip().casefold()]}
            report['steps'].append(step)
            report.update(active_node=frame['node_id'], active_stage='import')
            folder.mkdir()
            memory = folder/'memory.db'
            # The private predecessor is closed after import/search. Future writes
            # go to a new copy, so earlier search reports keep their memory identity.
            if previous is not None:
                shutil.copyfile(previous, memory)
            prefix['frames'].append(frame)
            prefix['accepted_observations'] += frame['accepted_observations']
            prefix['rejected_detections'] += len(frame['detections'])-frame['accepted_observations']
            step['import'] = import_report(memory, prefix)
            step['memory_sha256'] = file_hash(memory)
            report['active_stage'] = 'search'
            search = run_search(memory, mapping, label, folder/'search', simulated_xy=simulated_xy)
            step.update(search_sha256=file_hash(output/step['search_report']), query=search['query'],
                        search_status=search['status'], branch=search['branch'], branch_reason=search['branch_reason'],
                        outcomes=search['outcomes'])
            if file_hash(memory) != step['memory_sha256']:
                raise ValueError('Memory prefix changed during search')
            step.update(status='COMPLETE', duration_ms=(time.monotonic()-begin)*1000)
            previous = memory
        report['active_stage'] = 'final_validation'
        for step in report['steps']:
            if (file_hash(output/step['memory']) != step['memory_sha256']
                    or file_hash(output/step['search_report']) != step['search_sha256']):
                raise ValueError('Earlier replay evidence changed')
        if file_hash(observations) != source_hash:
            raise ValueError('Source observations changed during replay')
        report.update(status='REPLAY_COMPLETE', active_stage=None, active_node=None)
    except (ValueError, OSError, KeyError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'replay.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('observations', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--simulated-start-xy', type=float, nargs=2, required=True, metavar=('X_M', 'Y_M'))
    args = parser.parse_args()
    report = replay_search(args.observations.resolve(), args.mapping.resolve(), args.label,
                           args.output.resolve(), args.simulated_start_xy)
    print(json.dumps({'status': report['status'], 'steps': [
        {key: step[key] for key in ('node_id', 'source_stamp_ns', 'query', 'search_status', 'branch', 'branch_reason')}
        for step in report['steps']], 'report': str(args.output.resolve()/'replay.json'),
        'duration_ms': report['duration_ms']}, indent=2, allow_nan=False))
