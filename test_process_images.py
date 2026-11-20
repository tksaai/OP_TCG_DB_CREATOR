import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from process_images import (
    card_number_from_path,
    load_manifest_card_numbers,
    parse_card_image,
    process_images,
)


class ProcessImagesTest(unittest.TestCase):
    def test_card_number_from_path(self):
        self.assertEqual(card_number_from_path('OP18/OP18-001.jpg'), 'OP18-001')
        self.assertEqual(card_number_from_path('P/P-001.png'), 'P-001')
        self.assertEqual(card_number_from_path('OP18/OP18-001_small.jpg'), '')
        self.assertEqual(parse_card_image('OP18/OP18-001 (2).jpg'), ('OP18-001', 2))
        self.assertEqual(parse_card_image('OP18/OP18-001_p3.png'), ('OP18-001', 3))
        self.assertEqual(parse_card_image('OP18/OP18-001_r1.png'), ('OP18-001', 1001))

    def test_manifest_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory, 'image-manifest.json')
            manifest_path.write_text(
                json.dumps({'cards': {'OP18-001': [{'path': 'x.webp'}]}}),
                encoding='utf-8',
            )
            self.assertEqual(load_manifest_card_numbers(manifest_path), {'OP18-001'})

    def test_only_downloads_cards_missing_from_manifest_as_webp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.png'
            Image.new('RGBA', (16, 24), (255, 0, 0, 128)).save(source)

            file_list = [
                {'name': 'OP18-001.jpg', 'path': 'OP18/OP18-001.jpg', 'id': 'covered'},
                {
                    'name': 'OP18-001 (1).png',
                    'path': 'OP18/OP18-001 (1).png',
                    'id': 'covered-variant',
                },
                {
                    'name': 'OP18-001 (2).png',
                    'path': 'OP18/OP18-001 (2).png',
                    'id': 'missing-variant',
                },
                {'name': 'P-999.png', 'path': 'P/P-999.png', 'id': 'missing'},
                {'name': 'P-999_small.png', 'path': 'P/P-999_small.png', 'id': 'small'},
            ]
            list_path = root / 'file-list.json'
            list_path.write_text(json.dumps(file_list), encoding='utf-8')

            manifest_path = root / 'image-manifest.json'
            manifest_path.write_text(
                json.dumps({
                    'cards': {
                        'OP18-001': [
                            {'path': 'covered.webp', 'variantIndex': 0},
                            {'path': 'covered-variant.webp', 'variantIndex': 1},
                        ]
                    }
                }),
                encoding='utf-8',
            )

            downloads = []

            def fake_download(url, output):
                downloads.append(url)
                Path(output).write_bytes(source.read_bytes())

            output_path = root / 'CardsWebP'
            stats = process_images(
                json_path=list_path,
                output_path=output_path,
                exclude_keyword='_small',
                manifest_path=manifest_path,
                only_missing_manifest=True,
                output_format='webp',
                quality=90,
                delay=0,
                download_func=fake_download,
            )

            self.assertEqual(len(downloads), 2)
            self.assertTrue((output_path / 'P' / 'P-999.webp').exists())
            self.assertTrue((output_path / 'OP18' / 'OP18-001 (2).webp').exists())
            self.assertEqual(stats['processed'], 2)
            self.assertEqual(stats['manifest_skipped'], 2)
            self.assertEqual(stats['excluded'], 1)
            self.assertEqual(stats['errors'], 0)


if __name__ == '__main__':
    unittest.main()
