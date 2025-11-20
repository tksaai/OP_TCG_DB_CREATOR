import os
import glob
import shutil

# --- 設定 ---
DATA_DIR = 'data'
OUTPUT_FILE = 'OnePiece_Card_List_All.csv'

def clean_data():
    print("Starting data cleanup...")

    # 1. dataディレクトリ内のCSVファイルを削除
    if os.path.exists(DATA_DIR):
        # ディレクトリ内の全CSVファイルを取得
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

    # 2. 結合ファイル (OnePiece_Card_List_All.csv) を削除
    if os.path.exists(OUTPUT_FILE):
        try:
            os.remove(OUTPUT_FILE)
            print(f"Deleted: {OUTPUT_FILE}")
        except OSError as e:
            print(f"Error deleting {OUTPUT_FILE}: {e}")
    else:
        print(f"File not found: {OUTPUT_FILE}")

    print("Cleanup completed.")

if __name__ == "__main__":
    clean_data()