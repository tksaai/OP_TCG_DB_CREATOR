import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from PIL import Image


SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
CARD_IMAGE_PATTERN = re.compile(
    r'^((?:[A-Z0-9]+-\d+)|P)(?:(?: \((\d+)\))|(?:_p(\d+))|(?:_r(\d+)))?$',
    re.IGNORECASE,
)


def load_json(path, description):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        raise ValueError(f'{description}が見つかりません ({path})') from None
    except json.JSONDecodeError as error:
        raise ValueError(f'{description}の解析に失敗しました ({error})') from error


def parse_card_image(relative_path):
    match = CARD_IMAGE_PATTERN.fullmatch(Path(relative_path).stem)
    if not match:
        return '', -1

    card_number, local_variant, official_parallel, official_rarity = match.groups()
    if official_rarity:
        variant_index = 1000 + int(official_rarity)
    else:
        variant_index = int(local_variant or official_parallel or 0)
    return card_number.upper(), variant_index


def card_number_from_path(relative_path):
    return parse_card_image(relative_path)[0]


def load_manifest_card_numbers(manifest_path):
    return set(load_manifest_coverage(manifest_path))


def load_manifest_coverage(manifest_path):
    if not manifest_path:
        return {}

    manifest = load_json(manifest_path, '画像マニフェスト')
    cards = manifest.get('cards') if isinstance(manifest, dict) else None
    if not isinstance(cards, dict):
        raise ValueError('画像マニフェストに cards オブジェクトがありません')

    coverage = {}
    for card_number, variants in cards.items():
        normalized_number = str(card_number).upper()
        coverage[normalized_number] = set()
        if not isinstance(variants, list):
            continue
        for fallback_index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                continue
            try:
                variant_index = int(variant.get('variantIndex', fallback_index))
            except (TypeError, ValueError):
                variant_index = fallback_index
            coverage[normalized_number].add(variant_index)
    return coverage


def output_name(relative_path, output_format):
    path = Path(relative_path)
    if output_format == 'webp':
        return str(path.with_suffix('.webp'))
    if output_format == 'jpg':
        return str(path.with_suffix('.jpg'))
    return str(path)


def save_image(source_path, output_path, output_format, quality):
    with Image.open(source_path) as image:
        if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
            rgba = image.convert('RGBA')
            background = Image.new('RGB', rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel('A'))
            image_rgb = background
        else:
            image_rgb = image.convert('RGB')

        if output_format == 'webp':
            image_rgb.save(output_path, 'WEBP', quality=quality, method=6)
        else:
            image_rgb.save(output_path, 'JPEG', quality=quality, optimize=True)


def default_download(url, output):
    try:
        import gdown
    except ImportError as error:
        raise RuntimeError('gdown がインストールされていません') from error
    return gdown.download(url=url, output=output, quiet=True)


def process_images(
    json_path,
    output_path,
    exclude_keyword='',
    manifest_path='',
    only_missing_manifest=False,
    output_format='webp',
    quality=90,
    delay=1.0,
    download_func=None,
):
    print('=' * 30)
    print('処理を開始します...')

    file_list = load_json(json_path, 'リストファイル')
    if not isinstance(file_list, list):
        raise ValueError('リストファイルのルートは配列である必要があります')

    manifest_coverage = load_manifest_coverage(manifest_path)
    if only_missing_manifest and not manifest_path:
        raise ValueError('--only-missing-manifest には --manifest が必要です')

    print(f'リスト上の合計ファイル数: {len(file_list)}件')
    print(f'マニフェスト登録済みカード数: {len(manifest_coverage)}件')

    stats = {
        'processed': 0,
        'copied': 0,
        'existing': 0,
        'excluded': 0,
        'manifest_skipped': 0,
        'invalid': 0,
        'errors': 0,
    }
    downloader = download_func or default_download
    temp_dir = Path('./temp_download')
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for index, file_info in enumerate(file_list):
            if not isinstance(file_info, dict):
                stats['invalid'] += 1
                continue

            relative_path = str(file_info.get('path') or '')
            file_name = str(file_info.get('name') or '')
            file_id = str(file_info.get('id') or '')
            if not relative_path or not file_name or not file_id:
                print(f'[不正な項目] index={index}')
                stats['invalid'] += 1
                continue

            if exclude_keyword and exclude_keyword in relative_path:
                stats['excluded'] += 1
                continue

            card_number, variant_index = parse_card_image(relative_path)
            covered_variants = manifest_coverage.get(card_number, set())
            if only_missing_manifest and card_number and variant_index in covered_variants:
                stats['manifest_skipped'] += 1
                continue

            file_extension = Path(file_name).suffix.lower()
            destination_relative = output_name(relative_path, output_format)
            output_file = Path(output_path, destination_relative)
            if output_file.exists():
                stats['existing'] += 1
                continue

            output_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / f'{index:05d}_{file_name}'
            download_url = f'https://drive.google.com/uc?id={file_id}'
            print(f'[ダウンロード中] {relative_path}')

            try:
                downloader(download_url, str(temp_file))
                if not temp_file.exists():
                    raise RuntimeError('ダウンロード後のファイルが生成されませんでした')

                if file_extension in SUPPORTED_EXTENSIONS:
                    save_image(temp_file, output_file, output_format, quality)
                    stats['processed'] += 1
                    print(f'[変換完了] -> {destination_relative}')
                else:
                    shutil.move(str(temp_file), str(output_file))
                    stats['copied'] += 1
                    print(f'[コピー完了] -> {destination_relative}')
            except Exception as error:
                print(f'エラー: {relative_path} の処理失敗: {error}')
                stats['errors'] += 1
                if output_file.exists():
                    output_file.unlink()
            finally:
                if temp_file.exists():
                    temp_file.unlink()

            if delay > 0:
                time.sleep(delay)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    print('=' * 30)
    print('処理が完了しました。')
    print(f"新規変換: {stats['processed']}件, 新規コピー: {stats['copied']}件")
    print(
        f"既存スキップ: {stats['existing']}件, "
        f"マニフェスト登録済みスキップ: {stats['manifest_skipped']}件, "
        f"除外: {stats['excluded']}件"
    )
    print(f"不正な項目: {stats['invalid']}件, エラー: {stats['errors']}件")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Google Drive画像の安全な差分同期')
    parser.add_argument('--json', required=True, help='リストファイル(JSON)のパス')
    parser.add_argument('--output', required=True, help='出力フォルダのパス')
    parser.add_argument('--exclude', default='', help='除外する語句')
    parser.add_argument('--manifest', default='', help='本番の image-manifest.json')
    parser.add_argument(
        '--only-missing-manifest',
        action='store_true',
        help='マニフェストにカード番号がない画像だけを処理する',
    )
    parser.add_argument('--format', choices=('webp', 'jpg'), default='webp')
    parser.add_argument('--quality', type=int, default=90)
    parser.add_argument('--delay', type=float, default=1.0)
    args = parser.parse_args()

    if not 1 <= args.quality <= 100:
        parser.error('--quality は1から100の範囲で指定してください')
    if args.delay < 0:
        parser.error('--delay は0以上で指定してください')

    try:
        stats = process_images(
            json_path=args.json,
            output_path=args.output,
            exclude_keyword=args.exclude,
            manifest_path=args.manifest,
            only_missing_manifest=args.only_missing_manifest,
            output_format=args.format,
            quality=args.quality,
            delay=args.delay,
        )
    except ValueError as error:
        print(f'エラー: {error}')
        return 1

    return 1 if stats['errors'] or stats['invalid'] else 0


if __name__ == '__main__':
    sys.exit(main())
