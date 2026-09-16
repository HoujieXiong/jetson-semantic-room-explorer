"""Build and query a MobileCLIP-S0 semantic index of frozen scene-memory supports."""

import argparse
from contextlib import closing
import hashlib
import base64
import html
import importlib.metadata
import json
import math
from pathlib import Path
import resource
import sqlite3
import time

import numpy as np

from extract_mapped_rgbd import file_hash
from observe_rgbd_objects import load_frame
from scene_memory import canonical, check_schema, query


DIMENSION = 512
POLICY = {'model': 'mobileclip_s0', 'dtype': 'float32', 'device': 'cuda:0',
          'crop': 'Clipped detection box, floor lower / ceil upper exclusive; original RGB pixels',
          'samples': 'One geometric representative per object and source frame; exclude rejected depth and overlaps',
          'fusion': 'Unit-normalized equal mean of unit support vectors',
          'text': 'Exact user phrase, without label substitution or prompt expansion',
          'score': 'Cosine similarity, not probability or proof of presence'}


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


def unit_vector(value):
    value = np.asarray(value, dtype=np.float32)
    if value.shape != (DIMENSION,) or not np.isfinite(value).all():
        raise ValueError('Expected a finite 512-dimensional semantic vector')
    norm = float(np.linalg.norm(value))
    if not np.isfinite(norm) or norm < 1e-8:
        raise ValueError('Zero semantic vector or cancelling views')
    return value/norm


def crop_rgb(rgb, box):
    box = np.asarray(box, dtype=float)
    if (rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8
            or box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2])):
        raise ValueError('Expected RGB8 image and finite nonempty detection box')
    height, width = rgb.shape[:2]
    clipped = np.clip(box, [0, 0, 0, 0], [width, height, width, height])
    bounds = np.r_[np.floor(clipped[:2]), np.ceil(clipped[2:])].astype(int)
    x0, y0, x1, y1 = bounds
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Detection has no pixels inside source RGB')
    return np.ascontiguousarray(rgb[y0:y1, x0:x1]), bounds.tolist()


class MobileClipEncoder:
    """Concrete official S0 implementation shared by indexing and text queries."""
    def __init__(self, checkpoint):
        started = time.monotonic()
        import torch
        import mobileclip
        if not torch.cuda.is_available():
            raise RuntimeError('Jetson CUDA is required for this semantic measurement')
        checkpoint = checkpoint.resolve(strict=True)
        package = Path(mobileclip.__file__).parent
        sources = {str(p.relative_to(package)): file_hash(p) for p in sorted(package.rglob('*'))
                   if p.suffix in ('.py', '.json')}
        self.identity = {'checkpoint_sha256': file_hash(checkpoint), 'policy': POLICY,
                         'implementation_sha256': hashlib.sha256(canonical(sources).encode()).hexdigest(),
                         'packages': {name: importlib.metadata.version(name) for name in
                                      ('torch', 'torchvision', 'mobileclip', 'timm', 'open-clip-torch',
                                       'pillow', 'numpy', 'ftfy', 'regex')},
                         'device': torch.cuda.get_device_name(0)}
        self.model, _, self.preprocess = mobileclip.create_model_and_transforms(
            POLICY['model'], pretrained=str(checkpoint))
        self.model = self.model.to(POLICY['device']).eval()
        self.tokenizer = mobileclip.get_tokenizer(POLICY['model'])
        self.torch = torch
        torch.cuda.synchronize()
        self.load_ms = (time.monotonic()-started)*1000

    def encode(self, value, image=False):
        from PIL import Image
        started = time.monotonic()
        if not image and len(self.tokenizer.tokenizer.encode(value))+2 > self.tokenizer.context_length:
            raise ValueError('Text exceeds MobileCLIP context; shorten the phrase rather than truncate it')
        tensor = self.preprocess(Image.fromarray(value)).unsqueeze(0) if image else self.tokenizer([value])
        tensor = tensor.to(POLICY['device'])
        with self.torch.inference_mode():
            vector = (self.model.encode_image(tensor, normalize=True) if image
                      else self.model.encode_text(tensor, normalize=True))
        self.torch.cuda.synchronize()
        vector = unit_vector(vector[0].cpu().numpy())
        return vector, (time.monotonic()-started)*1000


def write_index(path, context, samples):
    if path.exists():
        raise FileExistsError(path)
    groups = {}
    for sample in samples:
        groups.setdefault(sample['object_id'], []).append(unit_vector(sample['vector']))
    if not groups:
        raise ValueError('No supporting observations to index')
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA user_version=1')
        connection.execute('CREATE TABLE metadata (context_json TEXT NOT NULL)')
        connection.execute('CREATE TABLE objects (object_id INTEGER PRIMARY KEY, vector BLOB NOT NULL, support_count INTEGER NOT NULL, view_consistency REAL NOT NULL)')
        connection.execute('''CREATE TABLE samples (node_id INTEGER NOT NULL, detection_index INTEGER NOT NULL,
            object_id INTEGER NOT NULL REFERENCES objects(object_id), evidence_json TEXT NOT NULL,
            vector BLOB NOT NULL, PRIMARY KEY(node_id, detection_index), UNIQUE(object_id, node_id))''')
        connection.execute('INSERT INTO metadata VALUES (?)', (canonical(context),))
        for object_id, vectors in sorted(groups.items()):
            mean = np.mean(vectors, axis=0)
            connection.execute('INSERT INTO objects VALUES (?, ?, ?, ?)',
                               (object_id, unit_vector(mean).astype('<f4').tobytes(), len(vectors), float(np.linalg.norm(mean))))
        for sample in samples:
            evidence = {k: v for k, v in sample.items() if k != 'vector'}
            connection.execute('INSERT INTO samples VALUES (?, ?, ?, ?, ?)',
                (sample['node_id'], sample['detection_index'], sample['object_id'], canonical(evidence),
                 unit_vector(sample['vector']).astype('<f4').tobytes()))


def build_index(memory, frames, model, output):
    from PIL import Image
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'memory_path': str(memory), 'frames_path': str(frames), 'samples': []}
    try:
        before = {'memory_sha256': file_hash(memory), 'frames_sha256': file_hash(frames), 'model_sha256': file_hash(model)}
        remembered = query(memory)
        with closing(sqlite3.connect(memory.as_uri()+'?mode=ro', uri=True)) as connection:
            check_schema(connection)
            supports = connection.execute("SELECT node_id, detection_index, object_id FROM associations WHERE decision IN ('new_object', 'nearest_match') ORDER BY node_id, detection_index").fetchall()
            evidence = {row[0]: json.loads(row[1]) for row in connection.execute('SELECT node_id, evidence_json FROM frames')}
        encoder = MobileClipEncoder(model)
        context = {**before, 'memory_context': remembered['context'], 'encoder': encoder.identity}
        report.update(context=context, load_ms=encoder.load_ms)
        (output/'crops').mkdir()
        samples, cached_node, rgb = [], None, None
        for node, index, object_id in supports:
            frame = evidence[node]
            if node != cached_node:
                rgb, _, _, _, provenance = load_frame(frames, node)
                if any(frame[k] != v for k, v in provenance.items()):
                    raise ValueError('Source RGB-D provenance differs from frozen memory')
                cached_node = node
            detection = next(d for d in frame['detections'] if d['detection_index'] == index)
            if detection['depth']['status'] != 'ACCEPTED':
                raise ValueError('Geometric support unexpectedly contains rejected depth')
            crop, bounds = crop_rgb(rgb, detection['box_xyxy'])
            path = output/'crops'/f'{node}_{index}.png'
            Image.fromarray(crop).save(path)
            vector, elapsed_ms = encoder.encode(crop, image=True)
            sample = {'object_id': object_id, 'node_id': node, 'detection_index': index,
                      'source_stamp_ns': frame['source_stamp_ns'], 'frame_sha256': frame['frame_sha256'],
                      'box_xyxy_exclusive': bounds, 'crop': str(path.relative_to(output)),
                      'crop_sha256': file_hash(path), 'rgb_pixels_sha256': hashlib.sha256(crop.tobytes()).hexdigest(),
                      'encode_ms': elapsed_ms}
            report['samples'].append(sample)
            samples.append({**sample, 'vector': vector})
        counts = {o['object_id']: sum(s['object_id'] == o['object_id'] for s in samples) for o in remembered['objects']}
        if counts != {o['object_id']: o['support_count'] for o in remembered['objects']}:
            raise ValueError('Semantic supports differ from geometric representatives')
        if before != {'memory_sha256': file_hash(memory), 'frames_sha256': file_hash(frames), 'model_sha256': file_hash(model)}:
            raise ValueError('Semantic source changed during indexing')
        write_index(output/'index.db', context, samples)
        latencies = [s['encode_ms'] for s in samples]
        report.update(status='INDEXED', index_sha256=file_hash(output/'index.db'), objects=len(counts), supports=len(samples),
                      first_encode_ms=latencies[0], warm_encode_ms={'count': len(latencies[1:]),
                      'median': float(np.median(latencies[1:])) if len(latencies)>1 else None,
                      'p95': float(np.percentile(latencies[1:], 95)) if len(latencies)>1 else None},
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      peak_cuda_allocated_bytes=encoder.torch.cuda.max_memory_allocated())
    except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'build.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def read_index(index, memory):
    report = json.loads((index/'build.json').read_text())
    if (report['status'] != 'INDEXED' or report['index_sha256'] != file_hash(index/'index.db')
            or report['context']['memory_sha256'] != file_hash(memory)):
        raise ValueError('Incomplete semantic index or changed index/memory')
    remembered = query(memory)
    with closing(sqlite3.connect((index/'index.db').as_uri()+'?mode=ro', uri=True)) as connection:
        context = json.loads(connection.execute('SELECT context_json FROM metadata').fetchone()[0])
        if context != report['context'] or context['memory_context'] != remembered['context']:
            raise ValueError('Semantic context differs from original memory')
        rows = connection.execute('SELECT object_id, vector, support_count, view_consistency FROM objects ORDER BY object_id').fetchall()
        samples = [(object_id, json.loads(evidence), np.frombuffer(vector, dtype='<f4')) for object_id, evidence, vector
                   in connection.execute('SELECT object_id, evidence_json, vector FROM samples ORDER BY node_id, detection_index')]
    objects = {o['object_id']: o for o in remembered['objects']}
    if set(objects) != {row[0] for row in rows} or any(objects[row[0]]['support_count'] != row[2] for row in rows):
        raise ValueError('Index and memory objects/support counts differ')
    return context, [(objects[oid], unit_vector(np.frombuffer(vector, dtype='<f4')), consistency)
                     for oid, vector, _, consistency in rows], samples


def rank_objects(text_vector, objects, samples):
    text_vector = unit_vector(text_vector)
    ranked = []
    for obj, vector, consistency in objects:
        views = [(float(np.dot(unit_vector(v), text_vector)), evidence)
                 for oid, evidence, v in samples if oid == obj['object_id']]
        if not views:
            raise ValueError('Indexed object has no supporting views')
        best = max(views, key=lambda row: row[0])
        ranked.append({'object_id': obj['object_id'], 'detector_label': obj['label'],
                       'cosine_similarity': float(np.dot(unit_vector(vector), text_vector)),
                       'view_similarity_min': min(v[0] for v in views), 'view_similarity_max': best[0],
                       'view_consistency': consistency, 'best_view': best[1],
                       'geometry': obj})
    return sorted(ranked, key=lambda row: (-row['cosine_similarity'], row['object_id']))


def write_query_review(queries, crop_root, output, limitation):
    """Keep reported selections separate from rejected diagnostic crops."""
    cards = []
    for row in queries:
        selected = row.get('selected_object_ids')
        if selected is not None and not set(selected) <= {c['object_id'] for c in row['ranking']}:
            raise ValueError('Query review selection is absent from its ranking')
        if selected is None:
            groups = [('Ranked candidates; no selection decision supplied', row['ranking'], False)]
        else:
            groups = [('Unconfirmed candidates' if selected else 'No candidate selected',
                       [c for c in row['ranking'] if c['object_id'] in selected], False),
                      ('Not selected — diagnostic images only',
                       [c for c in row['ranking'] if c['object_id'] not in selected], True)]
        parts = ['<h2>'+html.escape(row['text'])+'</h2>']
        for title, candidates, diagnostic in groups:
            if diagnostic and not candidates:
                continue
            cells = []
            for candidate in candidates[:3]:
                path = crop_root/candidate['best_view']['crop']
                if file_hash(path) != candidate['best_view']['crop_sha256']:
                    raise ValueError('Query review crop changed since indexing')
                encoded = base64.b64encode(path.read_bytes()).decode('ascii')
                cells.append(f'<td><img src="data:image/png;base64,{encoded}" alt="Recorded candidate crop">'
                             f'<p>ID {candidate["object_id"]} | cosine {candidate["cosine_similarity"]:.3f}</p>'
                             f'<p>Detector: {html.escape(candidate["detector_label"])}</p></td>')
            table = '<table><tr>'+''.join(cells)+'</tr></table>' if cells else ''
            parts.append('<details><summary>'+title+'</summary>'+table+'</details>' if diagnostic
                         else '<h3>'+title+'</h3>'+table)
        cards.append(''.join(parts))
    output.write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Semantic memory query review</title><style>body{font-family:sans-serif;max-width:1100px;margin:30px auto;background:#f4f5f7;color:#172033}'
        'table{width:100%;table-layout:fixed;background:white}td{padding:16px;vertical-align:top}img{width:100%;height:180px;object-fit:contain}</style>'
        '<h1>Semantic memory query review</h1><p>'+html.escape(limitation)+'</p>'
        '<p>Up to three records per group. Selected candidates are unconfirmed; scores are not confidence probabilities and detector labels can be wrong.</p>'
        +''.join(cards)+'</html>')


def query_index(index, memory, model, texts, output):
    if not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise ValueError('Provide nonempty text phrases')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'queries': [], 'index_path': str(index), 'memory_path': str(memory)}
    started = time.monotonic()
    try:
        context, objects, samples = read_index(index, memory)
        report.update(context=context, index_sha256=file_hash(index/'index.db'))
        if file_hash(model) != context['model_sha256']:
            raise ValueError('Text encoder weights differ from image encoder')
        encoder = MobileClipEncoder(model)
        if encoder.identity != context['encoder']:
            raise ValueError('Text/image encoder implementation or runtime differs')
        report['load_ms'] = encoder.load_ms
        for phrase in texts:
            vector, elapsed_ms = encoder.encode(phrase)
            report['queries'].append({'text': phrase, 'encode_ms': elapsed_ms,
                                      'text_vector': vector.tolist(),
                                      'ranking': rank_objects(vector, objects, samples)})
        if file_hash(memory) != context['memory_sha256'] or file_hash(index/'index.db') != report['index_sha256']:
            raise ValueError('Memory/index changed during query')
        report['limitation'] = 'Scores rank existing YOLO-proposed memory only; no calibrated presence/absence decision. Missed detections cannot be retrieved. Geometry remains provisional.'
        write_query_review(report['queries'], index, output/'queries.html', report['limitation'])
        report.update(status='RANKED', review='queries.html', review_sha256=file_hash(output/'queries.html'))
    except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'queries.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('build', 'query'):
        command = commands.add_parser(name)
        for argument in ('memory', 'model', 'output'):
            command.add_argument('--'+argument, type=Path, required=True)
        command.add_argument('--'+('frames' if name == 'build' else 'index'), type=Path, required=True)
        if name == 'query':
            command.add_argument('--text', action='append', required=True)
    args = parser.parse_args()
    common = (args.memory.resolve(), args.model.resolve(), args.output.resolve())
    result = (build_index(common[0], args.frames.resolve(), common[1], common[2]) if args.command == 'build'
              else query_index(args.index.resolve(), common[0], common[1], args.text, common[2]))
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
