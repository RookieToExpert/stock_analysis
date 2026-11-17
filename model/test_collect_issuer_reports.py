import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import collect_issuer_reports as collector


class EvidenceCache(unittest.TestCase):
    def test_cache_requires_matching_source_hash_and_readable_text(self):
        row={'code':'sh.600000','statDate':'2024-12-31','source':'https://example.test/report'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(collector.requests,'Session') as network:
            root=Path(tmp)
            with patch.object(collector,'root',root):
                for text, source, digest, expected in [
                    ('report '*100,row['source'],None,'cached'),
                    ('report '*100,'changed',None,'error:'),
                    ('report '*100,row['source'],'tampered','error:'),
                    ('Access denied',row['source'],None,'error:')]:
                    with gzip.open(root/'sh.600000-2024-12-31.txt.gz','wt') as f:f.write(text)
                    (root/'sh.600000-2024-12-31.json').write_text(json.dumps({
                        'source':source,'text_sha256':digest or hashlib.sha256(text.encode()).hexdigest()}))
                    self.assertTrue(collector.fetch(row)[1].startswith(expected))
                network.assert_not_called()
