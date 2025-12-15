import os
import glob

# --- 設定 (main.py と合わせる) ---
DATA_DIR = 'data'
OUTPUT_CSV = 'OnePiece_Card_List_All.csv'
OUTPUT_JSON = 'cards.json'
FURIGANA_DICT_FILE = 'furigana_dictionary.json'
VERIFIED_FILE = 'verified_cards.json'
UNVERIFIED_FILE = 'unverified_cards.json'

def clean_data():
    print("Starting data cleanup...")

    # 1. dataディレクトリ内のCSVファイルを削除
    if os.path.exists(DATA_DIR):
        files = glob.glob(os.path.join(DATA_DIR, '*.csv'))
        if files:
            for f in files:
                try:
                    os.remove(f)
                    print(f"Deleted: {f}")
                except OSError as e:
                    print(f"Error deleting {f}: {e}")
        else:
            print(f"No CSV files found in {DATA_DIR}.")
    else:
        print(f"Directory not found: {DATA_DIR}")

    # 2. 生成ファイル・管理ファイルの削除リスト
    files_to_delete = [
        OUTPUT_CSV,
        OUTPUT_JSON,
        VERIFIED_FILE,
        UNVERIFIED_FILE
    ]

    # 【注意】フリガナ辞書を削除すると、次回実行時に再度AIへの問い合わせが発生し時間がかかります。
    # 完全に初期化したい場合のみ、下のコメントアウトを外してください。
    files_to_delete.append(FURIGANA_DICT_FILE)

    for f_path in files_to_delete:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
                print(f"Deleted: {f_path}")
            except OSError as e:
                print(f"Error deleting {f_path}: {e}")
        else:
            print(f"File not found: {f_path}")

    print("Cleanup completed.")

if __name__ == "__main__":
    clean_data()