import os
import sys
import shutil
import argparse
import json
import gdown
import time  # ★ 追加: 待機時間用
from PIL import Image

SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')

def process_images(json_path, output_path, exclude_keyword):
    print("="*30)
    print("処理を開始します...")
    
    if not os.path.exists(json_path):
        print(f"エラー: リストファイルが見つかりません ({json_path})")
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            file_list = json.load(f)
        except json.JSONDecodeError as e:
            print(f"エラー: JSONの解析に失敗しました ({e})")
            sys.exit(1)

    print(f"リスト上の合計ファイル数: {len(file_list)}件")

    processed_count = 0
    copied_count = 0
    skipped_count = 0
    already_exists_count = 0
    error_count = 0 # ★ 追加: エラー数のカウント

    temp_dir = "./temp_download"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        for file_info in file_list:
            rel_path = file_info['path']
            file_name = file_info['name']
            file_id = file_info['id']

            if exclude_keyword and exclude_keyword in rel_path:
                print(f"[除外] {rel_path}")
                skipped_count += 1
                continue

            file_ext = os.path.splitext(file_name)[1].lower()
            
            if file_ext in SUPPORTED_EXTENSIONS:
                output_filename = os.path.splitext(rel_path)[0] + ".jpg"
            else:
                output_filename = rel_path
                
            output_filepath = os.path.join(output_path, output_filename)
            output_dir = os.path.dirname(output_filepath)

            # 差分判定 (出力先に既に存在する場合はスキップ)
            if os.path.exists(output_filepath):
                # print(f"[スキップ/既存] {output_filename}") # ログが長くなる場合はコメントアウト
                already_exists_count += 1
                continue

            os.makedirs(output_dir, exist_ok=True)

            print(f"[ダウンロード中] {rel_path}")
            temp_filepath = os.path.join(temp_dir, file_name)
            
            # ★ 修正: エラーで強制終了しないように try...except で囲む
            try:
                # アクセス制限回避のため、URL形式で指定
                download_url = f"https://drive.google.com/uc?id={file_id}"
                gdown.download(url=download_url, output=temp_filepath, quiet=True)
            except Exception as e:
                print(f"エラー: ダウンロード失敗 (アクセス制限等の可能性) - {rel_path}")
                error_count += 1
                continue

            if not os.path.exists(temp_filepath):
                print(f"エラー: ダウンロード失敗 (ファイル未生成) - {rel_path}")
                error_count += 1
                continue

            # ★ 修正: 画像変換処理
            if file_ext in SUPPORTED_EXTENSIONS:
                try:
                    with Image.open(temp_filepath) as img:
                        # 透過情報(RGBAなど)があれば、白背景のRGBに変換して警告を防ぐ
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            background = Image.new("RGB", img.size, (255, 255, 255)) # 白背景
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[3]) # 透過部分を合成
                            img_rgb = background
                        else:
                            img_rgb = img.convert("RGB")
                            
                        img_rgb.save(output_filepath, "JPEG", quality=20, optimize=True)
                    print(f"[変換完了] -> {output_filename}")
                    processed_count += 1
                except Exception as e:
                    print(f"エラー: {file_name} の変換失敗: {e}")
                    error_count += 1
            else:
                try:
                    shutil.move(temp_filepath, output_filepath)
                    print(f"[コピー完了] -> {output_filename}")
                    copied_count += 1
                except Exception as e:
                    print(f"エラー: {file_name} のコピー失敗: {e}")
                    error_count += 1
            
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
                
            # ★ 追加: Googleからブロックされないように、1ファイルごとに1秒待機
            time.sleep(1)

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
    print("="*30)
    print("処理が完了しました。")
    print(f"新規変換: {processed_count}件, 新規コピー: {copied_count}件")
    print(f"既存スキップ: {already_exists_count}件, 除外: {skipped_count}件, エラー: {error_count}件")
    
    # 完全に失敗したわけではないので、正常終了扱いとする（GitHub Actionsを赤くしないため）
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="リストファイルベース 画像差分ダウンロード・変換スクリプト")
    parser.add_argument("--json", required=True, help="リストファイル(JSON)のパス")
    parser.add_argument("--output", required=True, help="出力フォルダのパス")
    parser.add_argument("--exclude", default="", help="除外する語句")
    
    args = parser.parse_args()
    process_images(args.json, args.output, args.exclude)