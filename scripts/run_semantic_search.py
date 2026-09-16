"""Query image-text memory, plan for selected object IDs, and optionally publish ROS previews."""

import argparse
import json
import math
from pathlib import Path
import sqlite3
import time

from extract_mapped_rgbd import file_hash
from publish_search_preview import publish, select_preview
from run_offline_search import run_search
from semantic_memory import query_index


SELECTION_POLICY = {'min_cosine_similarity': .25, 'top_score_window': .02,
                    'calibrated': False,
                    'limitation': 'Experimental retrieval filter; passing scores do not establish identity or presence. No passing candidate does not prove absence.'}


def select_candidates(ranking):
    if not ranking:
        return []
    scores = [row['cosine_similarity'] for row in ranking]
    if any(not math.isfinite(s) or not -1.000001 <= s <= 1.000001 for s in scores):
        raise ValueError('Invalid cosine similarity')
    threshold = max(SELECTION_POLICY['min_cosine_similarity'], max(scores)-SELECTION_POLICY['top_score_window'])
    return [row['object_id'] for row in ranking if row['cosine_similarity'] >= threshold]


def run(index, memory, model, mapping, text, output, node_id=None, simulated_xy=None, ros_preview=False):
    if (node_id is None) == (simulated_xy is None):
        raise ValueError('Provide exactly one recorded camera node or simulated start')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'text': text, 'dry_run': True, 'motion_executed': False}
    started = time.monotonic()
    try:
        semantic = query_index(index, memory, model, [text], output/'semantic')
        ids = select_candidates(semantic['queries'][0]['ranking'])
        selection = {'object_ids': ids, 'policy': SELECTION_POLICY, 'text': text,
                     'status': 'CANDIDATES_SELECTED' if ids else 'NO_CANDIDATE_ABOVE_THRESHOLD',
                     'query_report_sha256': file_hash(output/'semantic/queries.json'),
                     'index_sha256': semantic['index_sha256']}
        report['semantic_selection'] = selection
        search = run_search(memory, mapping, text, output/'search', node_id, simulated_xy, ids)
        if search['memory_sha256'] != semantic['context']['memory_sha256']:
            raise ValueError('Memory changed between semantic retrieval and planning')
        report.update(search_status=search['status'], branch=search['branch'], outcomes=search['outcomes'],
                      search_sha256=file_hash(output/'search/search.json'))
        if ros_preview:
            report['publication'] = {'status': 'INCOMPLETE'}
            decision = select_preview(search, output/'search')
            decision['semantic_selection'] = selection
            publish(decision, 5, 10, report['publication'])
        report['status'] = 'SEMANTIC_SEARCH_COMPLETE'
    except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'semantic_search.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index', 'memory', 'model', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--text', required=True)
    start = parser.add_mutually_exclusive_group(required=True)
    start.add_argument('--start-node', type=int)
    start.add_argument('--simulated-start-xy', type=float, nargs=2, metavar=('X_M', 'Y_M'))
    parser.add_argument('--publish-preview', action='store_true')
    args = parser.parse_args()
    result = run(args.index.resolve(), args.memory.resolve(), args.model.resolve(), args.mapping.resolve(),
                 args.text, args.output.resolve(), args.start_node, args.simulated_start_xy, args.publish_preview)
    print(json.dumps({'status': result['status'], 'selection': result.get('semantic_selection'),
                      'search_status': result.get('search_status'), 'output': str(args.output)}))
