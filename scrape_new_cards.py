import os
import json
import requests
import time
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
# Google Sheetsの設定 (GCPでサービスアカウントを作成し、JSONキーを取得・Secretsに登録してください)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
# GitHub ActionsのSecretsからクレデンシャルを取得する前提
CREDENTIALS_JSON = os.environ.get('GSPREAD_CREDENTIALS') 
SHEET_NAME = 'TargetSets' # スプレッドシート名

# 画像保存先
IMAGE_DIR = 'OP_TCG_DB/temp_images'
JSON_OUTPUT = 'OP_TCG_DB/new_cards.json'

def setup_gspread():
    if not CREDENTIALS_JSON:
        print("GSPREAD_CREDENTIALS not found.")
        return None
    creds_dict = json.loads(CREDENTIALS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def download_image(img_url, file_name):
    if not os.path.exists(IMAGE_DIR):
        os.makedirs(IMAGE_DIR)
    
    path = os.path.join(IMAGE_DIR, file_name)
    if os.path.exists(path):
        return path # 既に存在すればスキップ

    try:
        response = requests.get(img_url)
        if response.status_code == 200:
            with open(path, 'wb') as f:
                f.write(response.content)
            return path
    except Exception as e:
        print(f"Error downloading {img_url}: {e}")
    return None

def scrape_site(url, set_name):
    print(f"Scraping {set_name} from {url}...")
    cards = []
    try:
        res = requests.get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # NOTE: 以下のセレクタは対象サイトの構造に合わせて修正してください
        # 例: カードリストの各アイテムを取得
        card_elements = soup.select('.card_list_item') # 仮のクラス名

        for el in card_elements:
            try:
                # 仮のデータ抽出ロジック
                # ID取得 (例: OP01-001)
                card_id = el.select_one('.card_number').text.strip()
                name = el.select_one('.card_name').text.strip()
                img_src = el.select_one('img')['src']
                
                # 画像ファイル名生成
                img_filename = f"{card_id.replace('/', '_')}.jpg"
                
                # 画像ダウンロード
                download_image(img_src, img_filename)

                # カードデータ構築 (既存のcards.jsonの形式に合わせる)
                card_data = {
                    "uniqueId": card_id, # 仮ID
                    "cardNumber": card_id,
                    "cardName": name,
                    "rarity": "UNK", # 必要に応じて取得
                    "color": ["Unknown"], 
                    "costLifeValue": "",
                    "power": "",
                    "counter": "",
                    "attribute": "",
                    "features": [set_name], # 特徴にセット名を入れておく
                    "effectText": "",
                    "imageUrl": f"temp_images/{img_filename}", # 相対パス
                    "isNew": True # アプリ側で区別するためのフラグ
                }
                cards.append(card_data)
            except AttributeError:
                continue
                
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    
    return cards

def main():
    client = setup_gspread()
    if not client:
        return

    sheet = client.open(SHEET_NAME).sheet1
    rows = sheet.get_all_records() # ヘッダー: SetName, URL を想定

    all_new_cards = []

    for row in rows:
        set_name = row.get('SetName')
        url = row.get('URL')
        if url:
            cards = scrape_site(url, set_name)
            all_new_cards.extend(cards)
            time.sleep(2) # マナーとしてウェイト

    # JSON保存
    with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(all_new_cards, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_new_cards)} cards to {JSON_OUTPUT}")

if __name__ == "__main__":
    main()