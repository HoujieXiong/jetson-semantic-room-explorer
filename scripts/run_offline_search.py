"""Query frozen scene memory and preview an object route or frontier search in one command."""

import argparse
import json
from pathlib import Path
import sqlite3
import time

from extract_mapped_rgbd import file_hash
from preview_frontier_search import preview_frontiers
from preview_search_goal import preview
from preview_search_route import preview_route


def run_search(memory, mapping, label, output, node_id=None, simulated_xy=None):
    if (node_id is None) == (simulated_xy is None):
        raise ValueError('Provide exactly one recorded camera node or simulated start')
    requested_start = {'node_id': node_id, 'simulated_xy_m': simulated_xy}
    json.dumps(requested_start, allow_nan=False)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'branch': None, 'active_stage': 'goal',
              'query_label': label, 'requested_start': requested_start,
              'memory_path': str(memory), 'mapping_path': str(mapping),
              'map_frame': 'map', 'coordinate_unit': 'meter', 'dry_run': True,
              'observation_executed': False, 'motion_executed': False, 'new_coverage_measured': False,
              'stages': [{'name': 'goal', 'report': 'goal/preview.json', 'status': 'INCOMPLETE'}],
              'outcomes': [],
              'limitation': 'Frozen-data planning only. Simulated starts are test fixtures; recorded camera projections are not current robot localization. Physical visibility, traversal and object identity remain unverified.'}
    try:
        source = preview(memory, mapping, label, output/'goal')
        report['stages'][0]['status'] = source['status']
        report['query'] = {'status': source['query_status'],
                           'candidate_ids': [obj['object_id'] for obj in source['object_candidates']],
                           'goal_status': source['status'], 'reason': source.get('reason'),
                           'goal_rejections': [{'object_id': row['object_id'], 'reason': row['reason']}
                                               for row in source['results'] if row['goal'] is None]}
        report['memory_sha256'] = source['memory_sha256']
        if source['status'] == 'PREVIEW_READY':
            report.update(branch='object_route', branch_reason='object_goal_available', active_stage='route')
            report['stages'].append({'name': 'route', 'report': 'route/route.json', 'status': 'INCOMPLETE'})
            result = preview_route(output/'goal/preview.json', memory, mapping, output/'route', node_id, simulated_xy)
            report['outcomes'] = [{'object_id': row['object_id'], 'status': row['status'],
                                   'reason': row.get('reason'), 'goal': goal['goal'], 'length_m': row.get('length_m')}
                                  for goal, row in zip(source['results'], result['results'])]
        elif source['status'] == 'NO_GOAL':
            report.update(branch='frontier', branch_reason=source.get('reason', 'no_object_goal'), active_stage='frontier')
            report['stages'].append({'name': 'frontier', 'report': 'frontier/frontier.json', 'status': 'INCOMPLETE'})
            result = preview_frontiers(output/'goal/preview.json', memory, mapping, output/'frontier', node_id, simulated_xy)
            exploration = result['exploration']
            report['outcomes'] = [{'status': result['status'], 'reason': exploration.get('reason'),
                                   'goal': exploration['goal'],
                                   'length_m': exploration['route']['length_m'] if exploration['route'] else None}]
        else:
            raise ValueError('Expected a completed object-goal decision')
        report['stages'][-1]['status'] = result['status']
        report['start'] = result['start']
        # Paths are relative to search.json; full candidates, source observations,
        # map/pose hashes and route/ray witnesses remain in the original stage reports.
        for stage in report['stages']:
            path = output/stage['report']
            stage.update(sha256=file_hash(path),
                         images=[str(p.relative_to(output)) for p in sorted(path.parent.glob('*.png'))])
        report.update(status=result['status'], active_stage=None)
    except (ValueError, OSError, KeyError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'search.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('memory', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--label', required=True)
    start = parser.add_mutually_exclusive_group(required=True)
    start.add_argument('--start-node', type=int, help='Recorded camera projection; not current robot localization')
    start.add_argument('--simulated-start-xy', type=float, nargs=2, metavar=('X_M', 'Y_M'),
                       help='Explicit simulated planning fixture in map meters')
    args = parser.parse_args()
    report = run_search(args.memory.resolve(), args.mapping.resolve(), args.label, args.output.resolve(),
                        args.start_node, args.simulated_start_xy)
    print(json.dumps({'status': report['status'], 'branch': report['branch'],
                      'branch_reason': report['branch_reason'], 'outcomes': report['outcomes'],
                      'report': str(args.output.resolve()/'search.json'), 'duration_ms': report['duration_ms']},
                     indent=2, allow_nan=False))
