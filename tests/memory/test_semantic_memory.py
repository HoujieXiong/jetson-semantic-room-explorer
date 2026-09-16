"""Known crop pixels, semantic fusion/ranking and persistent evidence boundaries."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from semantic_memory import MobileClipEncoder, crop_rgb, rank_objects, read_index, square_pad_rgb, unit_vector, write_index, write_query_review
from run_semantic_search import select_candidates


def axis(index):
    value = np.zeros(512, dtype=np.float32)
    value[index] = 1
    return value


class SemanticMathTests(unittest.TestCase):
    def test_clipped_fractional_crop_preserves_rgb_pixels_and_exclusive_bounds(self):
        rgb = np.arange(4*5*3, dtype=np.uint8).reshape(4, 5, 3)
        crop, box = crop_rgb(rgb, [-2, 1.2, 3.1, 8])
        self.assertEqual(box, [0, 1, 4, 4])
        np.testing.assert_array_equal(crop, rgb[1:4, 0:4])
        self.assertTrue(crop.flags.c_contiguous)

    def test_invalid_or_outside_crops_fail(self):
        rgb = np.zeros((4, 5, 3), dtype=np.uint8)
        for box in ([5, 0, 9, 2], [0, 0, 0, 1], [0, 0, float('nan'), 1], [0, 1, 2]):
            with self.assertRaises(ValueError):
                crop_rgb(rgb, box)
        with self.assertRaises(ValueError):
            crop_rgb(rgb.astype(float), [0, 0, 2, 2])

    def test_normalization_and_degenerate_embeddings(self):
        np.testing.assert_array_equal(unit_vector(axis(2)*3), axis(2))
        for value in (np.zeros(512), np.ones(511), np.full(512, np.nan), np.full(512, np.inf), np.full(512, 1e30)):
            with self.assertRaises(ValueError):
                unit_vector(value)

    def test_square_padding_preserves_complete_wide_tall_and_square_rgb(self):
        wide = np.full((2, 5, 3), [11, 23, 37], dtype=np.uint8)
        padded = square_pad_rgb(wide)
        self.assertEqual(padded.shape, (5, 5, 3))
        np.testing.assert_array_equal(padded[1:3], wide)
        self.assertFalse(padded[[0, 3, 4]].any())
        tall = wide.transpose(1, 0, 2)
        np.testing.assert_array_equal(square_pad_rgb(tall), padded.transpose(1, 0, 2))
        square = np.arange(27, dtype=np.uint8).reshape(3, 3, 3)
        np.testing.assert_array_equal(square_pad_rgb(square), square)

    def test_padding_rejects_empty_or_non_rgb8_crops_and_invalid_modes(self):
        for shape, dtype in [((0, 2, 3), np.uint8), ((2, 0, 3), np.uint8),
                             ((2, 2), np.uint8), ((2, 2, 4), np.uint8), ((2, 2, 3), float)]:
            with self.assertRaisesRegex(ValueError, 'nonempty RGB8'):
                square_pad_rgb(np.zeros(shape, dtype=dtype))
        for mode in (1, 'true', None):
            with self.assertRaisesRegex(ValueError, 'must be a boolean'):
                MobileClipEncoder(Path('unused.pt'), square_pad=mode)

    def test_semantic_ranking_is_independent_of_detector_label_and_keeps_geometry(self):
        objects = [({'object_id': 2, 'label': 'bottle', 'map_point_m': [1, 2, 3]}, axis(0), 1),
                   ({'object_id': 1, 'label': 'microwave', 'map_point_m': [4, 5, 6]}, axis(1), .7)]
        samples = [(2, {'crop': 'bottle.png'}, axis(0)), (1, {'crop': 'container.png'}, axis(1))]
        result = rank_objects(axis(1), objects, samples)
        self.assertEqual([r['object_id'] for r in result], [1, 2])
        self.assertEqual([r['cosine_similarity'] for r in result], [1, 0])
        self.assertEqual(result[0]['geometry']['map_point_m'], [4, 5, 6])
        self.assertEqual(result[0]['best_view']['crop'], 'container.png')

    def test_equal_scores_tie_by_id_and_missing_support_fails(self):
        objects = [({'object_id': i, 'label': 'chair'}, axis(0), 1) for i in (2, 1)]
        samples = [(i, {}, axis(0)) for i in (2, 1)]
        self.assertEqual([r['object_id'] for r in rank_objects(axis(0), objects, samples)], [1, 2])
        with self.assertRaisesRegex(ValueError, 'supporting views'):
            rank_objects(axis(0), objects, samples[:1])

    def test_threshold_keeps_ambiguity_and_can_select_nothing(self):
        ranking = [{'object_id': i, 'cosine_similarity': s} for i, s in [(1, .4), (2, .39), (3, .3)]]
        self.assertEqual(select_candidates(ranking), [1, 2])
        self.assertEqual(select_candidates([{'object_id': 1, 'cosine_similarity': .24}]), [])
        self.assertEqual(select_candidates([]), [])
        with self.assertRaises(ValueError):
            select_candidates([{'object_id': 1, 'cosine_similarity': float('nan')}])


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        crop = self.root/'crop.png'
        Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8)).save(crop)
        self.candidate = {'object_id': 1, 'cosine_similarity': .157531,
                          'detector_label': 'refrigerator',
                          'best_view': {'crop': crop.name, 'crop_sha256': hashlib.sha256(crop.read_bytes()).hexdigest()}}
        self.output = self.root/'review.html'

    def test_no_selection_has_no_result_image_but_keeps_closed_diagnostics(self):
        write_query_review([{'text': 'a bowl', 'ranking': [self.candidate], 'selected_object_ids': []}],
                           self.root, self.output, 'Unconfirmed identity')
        visible, diagnostic = self.output.read_text().split('<details>')
        self.assertIn('No candidate selected', visible)
        self.assertNotIn('<img ', visible)
        self.assertIn('Not selected', diagnostic)
        self.assertIn('<img ', diagnostic)
        self.assertNotIn('<details open', self.output.read_text())

    def test_reported_selection_is_unconfirmed_and_not_recomputed_from_score(self):
        write_query_review([{'text': 'a fridge', 'ranking': [self.candidate], 'selected_object_ids': [1]}],
                           self.root, self.output, 'Unconfirmed identity')
        page = self.output.read_text()
        self.assertIn('Unconfirmed candidates', page)
        self.assertEqual(page.count('<img '), 1)
        self.assertNotIn('<details>', page)

    def test_ranking_only_keeps_its_meaning_and_changed_diagnostic_crop_fails(self):
        row = {'text': '<bowl>', 'ranking': [self.candidate]}
        write_query_review([row], self.root, self.output, 'Unconfirmed identity')
        self.assertIn('no selection decision supplied', self.output.read_text())
        self.assertIn('&lt;bowl&gt;', self.output.read_text())
        row['selected_object_ids'] = [2]
        with self.assertRaisesRegex(ValueError, 'absent from its ranking'):
            write_query_review([row], self.root, self.output, '')
        row['selected_object_ids'] = []
        (self.root/'crop.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'crop changed'):
            write_query_review([row], self.root, self.output, '')


class SemanticPersistenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.samples = [{'node_id': i+1, 'detection_index': 0, 'object_id': 7,
                         'source_stamp_ns': (i+1)*10**9, 'vector': axis(i)} for i in range(2)]

    def test_reopened_fusion_retains_both_views_and_known_agreement(self):
        path = self.root/'index.db'
        write_index(path, {'test': 'identity'}, self.samples)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            vector, count, agreement = connection.execute('SELECT vector, support_count, view_consistency FROM objects').fetchone()
            value = np.frombuffer(vector, dtype='<f4')
            self.assertAlmostEqual(value[0], 2**-.5)
            self.assertAlmostEqual(value[1], 2**-.5)
            self.assertEqual(count, 2)
            self.assertAlmostEqual(agreement, 2**-.5)
            self.assertEqual(connection.execute('SELECT count(*) FROM samples').fetchone()[0], 2)
        with self.assertRaises(FileExistsError):
            write_index(path, {}, self.samples)

    def test_same_frame_support_is_not_double_counted(self):
        self.samples[1].update(node_id=1, detection_index=1)
        with self.assertRaises(sqlite3.IntegrityError):
            write_index(self.root/'index.db', {}, self.samples)

    def test_cancelling_views_and_empty_index_fail(self):
        self.samples[1]['vector'] = -axis(0)
        with self.assertRaisesRegex(ValueError, 'cancelling'):
            write_index(self.root/'cancelled.db', {}, self.samples)
        with self.assertRaisesRegex(ValueError, 'No supporting'):
            write_index(self.root/'empty.db', {}, [])

    def test_incomplete_index_never_becomes_queryable(self):
        (self.root/'build.json').write_text(json.dumps({'status': 'INCOMPLETE'}))
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            read_index(self.root, self.root/'missing_memory.db')
        self.assertFalse((self.root/'missing_memory.db').exists())


if __name__ == '__main__':
    unittest.main()
