"""Saved-map membership must not inherit a transient online graph endpoint."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from extract_mapped_rgbd import frozen_graph_ids


class FrozenGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name)/'map.db'
        self.graph = [{'node_id': node} for node in (1, 9, 60)]

    def save(self, ids=(1, 9), version='0.23.7', blob=None):
        if blob is None:
            blob = zlib.compress(struct.pack('<'+'i'*len(ids), *ids))+struct.pack('<iii', 1, len(ids), 4)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS Admin(version TEXT,opt_ids BLOB)')
            connection.execute('DELETE FROM Admin')
            connection.execute('INSERT INTO Admin VALUES(?,?)', (version, blob))
            connection.commit()

    def test_online_endpoint_can_be_absent_from_saved_graph_without_changing_database(self):
        self.save()
        before = self.database.read_bytes()
        self.assertEqual(frozen_graph_ids(self.database, self.graph), {1, 9})
        self.assertEqual(self.database.read_bytes(), before)

    def test_identical_online_and_saved_membership_remains_supported(self):
        self.save(ids=(1, 9, 60))
        self.assertEqual(frozen_graph_ids(self.database, self.graph), {1, 9, 60})

    def test_duplicate_invalid_and_unknown_ids_are_rejected(self):
        for ids in ((1, 1), (1, 0), (1, -9), (1, 999)):
            with self.subTest(ids=ids):
                self.save(ids=ids)
                with self.assertRaisesRegex(ValueError, 'duplicate, invalid or absent'):
                    frozen_graph_ids(self.database, self.graph)

    def test_unsupported_version_and_matrix_layout_are_rejected(self):
        self.save(version='unknown')
        with self.assertRaisesRegex(ValueError, '0.23.7'):
            frozen_graph_ids(self.database, self.graph)
        for footer in ((2, 1, 4), (1, 2, 5), (1, 0, 4)):
            self.save(blob=zlib.compress(struct.pack('<ii', 1, 9))+struct.pack('<iii', *footer))
            with self.assertRaisesRegex(ValueError, 'matrix layout'):
                frozen_graph_ids(self.database, self.graph)

    def test_truncated_or_extra_compressed_data_cannot_silently_pass(self):
        packed = zlib.compress(struct.pack('<ii', 1, 9))
        footer = struct.pack('<iii', 1, 2, 4)
        for blob in (packed[:-1]+footer, packed+b'extra'+footer, packed+struct.pack('<iii', 1, 3, 4), b'bad data'+footer):
            with self.subTest(blob=blob):
                self.save(blob=blob)
                with self.assertRaises(ValueError): frozen_graph_ids(self.database, self.graph)

    def test_missing_database_is_not_created(self):
        with self.assertRaises(sqlite3.OperationalError):
            frozen_graph_ids(self.database, self.graph)
        self.assertFalse(self.database.exists())


if __name__ == '__main__':
    unittest.main()
