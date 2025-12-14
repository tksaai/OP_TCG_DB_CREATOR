import os
import glob

# --- 設定 (main.py と合わせる) ---
DATA_DIR = 'data'
OUTPUT_CSV = 'OnePiece_Card_List_All.csv'
OUTPUT_JSON = 'cards.json'
# 注意: フリガナ辞書を削除すると、次回実行時に再度AIへの問い合わせが発生し時間がかかります。
# 完全に初期化したい場合のみ、下のコメントアウトを外してください。
FURIGANA_DICT_FILE = 'furigana_dictionary.json' 

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

    # 2. 結合CSVファイルを削除
    if os.path.exists(OUTPUT_CSV):
        try:
            os.remove(OUTPUT_CSV)
            print(f"Deleted: {OUTPUT_CSV}")
        except OSError as e:
            print(f"Error deleting {OUTPUT_CSV}: {e}")
    else:
        print(f"File not found: {OUTPUT_CSV}")

    # 3. JSONファイルを削除 (追加)
    if os.path.exists(OUTPUT_JSON):
        try:
            os.remove(OUTPUT_JSON)
            print(f"Deleted: {OUTPUT_JSON}")
        except OSError as e:
            print(f"Error deleting {OUTPUT_JSON}: {e}")
    else:
        print(f"File not found: {OUTPUT_JSON}")

    # 4. フリガナ辞書の削除 (通常はコメントアウト推奨)
    # 辞書まで消すとAIコストと時間がかかるため、通常は残します。
    if os.path.exists(FURIGANA_DICT_FILE):
        try:
            os.remove(FURIGANA_DICT_FILE)
            print(f"Deleted: {FURIGANA_DICT_FILE}")
        except OSError as e:
            print(f"Error deleting {FURIGANA_DICT_FILE}: {e}")

    print("Cleanup completed.")

if __name__ == "__main__":
    clean_data()