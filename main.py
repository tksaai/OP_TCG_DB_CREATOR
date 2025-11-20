import os
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# --- 設定 ---
BASE_URL = 'https://www.onepiece-cardgame.com/cardlist/'
DATA_DIR = 'data'
OUTPUT_FILE = 'OnePiece_Card_List_All.csv'

# 毎回必ず取得するシリーズのコード（プロモーション、限定商品）
ALWAYS_FETCH_CODES = ['550901', '550801']

def get_all_series_list():
    """
    公式サイトからシリーズ（収録弾）のリストを取得する
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        print("Fetching series list...")
        response = requests.get(BASE_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        series_options = []
        select_tag = soup.find('select', {'name': 'series'})
        if select_tag:
            options = select_tag.find_all('option')
            for opt in options:
                val = opt.get('value')
                name = opt.get_text(strip=True)
                if val and val.isdigit():
                    series_options.append({'code': val, 'name': name})
        
        return series_options
    except Exception as e:
        print(f"Error fetching series list: {e}")
        return []

def fetch_and_parse_cards(series_code):
    """
    指定されたシリーズコードのカードデータを取得・解析する
    """
    url = f"{BASE_URL}?series={series_code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching URL {url}: {e}")
        return pd.DataFrame()

    card_modals = soup.find_all('dl', class_='modalCol')
    data = []
    
    for modal in card_modals:
        try:
            # --- 基本情報の取得 ---
            info_col = modal.find('dt').find('div', class_='infoCol')
            spans = info_col.find_all('span')
            
            card_id = spans[0].get_text(strip=True)
            rarity = spans[1].get_text(strip=True)
            card_type = spans[2].get_text(strip=True)
            card_name = modal.find('dt').find('div', class_='cardName').get_text(strip=True)
            
            # --- 詳細情報の取得 ---
            back_col = modal.find('dd').find('div', class_='backCol')
            
            # コスト / ライフ (レイアウト通りに分割)
            cost_life_div = back_col.find('div', class_='cost')
            cost_life_type = ""
            cost_life_value = ""
            
            if cost_life_div:
                h3_tag = cost_life_div.find('h3')
                if h3_tag:
                    # h3タグの中身（例: "ライフ" や "コスト"）
                    cost_life_type = h3_tag.get_text(strip=True)
                    # 全体テキストからh3部分を除去して値を取得（例: "4"）
                    full_text = cost_life_div.get_text(strip=True)
                    cost_life_value = full_text.replace(cost_life_type, '')
                else:
                    cost_life_value = cost_life_div.get_text(strip=True)

            # 属性
            attribute_div = back_col.find('div', class_='attribute')
            attribute_img = attribute_div.find('img')
            attribute = attribute_img.get('alt', '') if attribute_img else attribute_div.get_text(strip=True).replace('属性', '')
            
            # その他パラメータ
            power = back_col.find('div', class_='power').get_text(strip=True).replace('パワー', '')
            counter = back_col.find('div', class_='counter').get_text(strip=True).replace('カウンター', '')
            color = back_col.find('div', class_='color').get_text(strip=True).replace('色', '')
            feature = back_col.find('div', class_='feature').get_text(strip=True).replace('特徴', '')
            text = back_col.find('div', class_='text').get_text(strip=True).replace('テキスト', '')
            
            trigger_div = back_col.find('div', class_='trigger')
            trigger = trigger_div.get_text(strip=True).replace('トリガー', '') if trigger_div else ""
            
            get_info_div = back_col.find('div', class_='getInfo')
            set_info = get_info_div.get_text(strip=True).replace('入手情報', '') if get_info_div else ""

            row = {
                'CardID': card_id,
                'Name': card_name,
                'Rarity': rarity,
                'Type': card_type,
                'Cost_Life_Type': cost_life_type,   # コスト/ライフ種別
                'Cost_Life_Value': cost_life_value, # コスト/ライフ値
                'Attribute': attribute,
                'Power': power,
                'Counter': counter,
                'Color': color,
                'Feature': feature,
                'Text': text,
                'Trigger': trigger,
                'SetInfo': set_info,
                'ImageFileID': ''
            }
            data.append(row)
            
        except Exception as e:
            print(f"Skipping a card in {series_code}: {e}")
            continue

    return pd.DataFrame(data)

def process_duplicates(df):
    """
    重複判定ロジック
    """
    if df.empty:
        return df

    # 優先度付け: SPを含む場合は 1、それ以外は 0
    df['SortPriority'] = df['Rarity'].apply(lambda x: 1 if 'SP' in str(x) else 0)
    
    # ID順、次に優先度順で並び替え
    df_sorted = df.sort_values(by=['CardID', 'SortPriority']).reset_index(drop=True)
    
    # 重複フラグ作成
    df_sorted['IsDuplicate'] = df_sorted.duplicated(subset=['CardID'], keep='first')
    
    return df_sorted.drop(columns=['SortPriority'])

def main():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 1. 全シリーズリストの取得
    series_list = get_all_series_list()
    if not series_list:
        print("No series found. Exiting.")
        return

    print(f"Found {len(series_list)} series.")

    # 2. 各シリーズのデータを取得・保存
    for series in series_list:
        code = series['code']
        name = series['name']
        file_path = os.path.join(DATA_DIR, f"{code}.csv")
        
        is_always_fetch = code in ALWAYS_FETCH_CODES
        file_exists = os.path.exists(file_path)

        if not is_always_fetch and file_exists:
            print(f"[Skip] {name} ({code}) - Already fetched.")
            continue
        
        print(f"[Fetch] {name} ({code})...")
        df = fetch_and_parse_cards(code)
        
        if not df.empty:
            df['SeriesCode'] = code
            df['SeriesName'] = name
            df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"  -> Saved {len(df)} cards to {file_path}")
        else:
            print(f"  -> No data found for {code}")
        
        time.sleep(2)

    # 3. 全データの結合と重複判定
    print("Merging all data...")
    all_files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    
    if all_files:
        df_list = [pd.read_csv(f) for f in all_files]
        df_all = pd.concat(df_list, ignore_index=True)
        
        df_final = process_duplicates(df_all)
        
        df_final.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"Done! Total {len(df_final)} cards saved to {OUTPUT_FILE}")
    else:
        print("No data files to merge.")

if __name__ == "__main__":
    main()