import os
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import copy

# --- 設定 ---
BASE_URL = 'https://www.onepiece-cardgame.com/cardlist/'
DATA_DIR = 'data'
OUTPUT_FILE = 'OnePiece_Card_List_All.csv'

# 毎回必ず取得するシリーズのコード（プロモーション、限定商品）
ALWAYS_FETCH_CODES = ['550901', '550801']

def clean_text(text):
    """
    文字列からHTMLタグのような形式を正規表現で削除し、余分な空白を整理する
    """
    if not text:
        return ""
    # 文字列化
    text = str(text)
    # <...> の形式をすべて空文字に置換
    text = re.sub(r'<[^>]+>', '', text)
    # 連続する空白・改行を1つのスペースに置換
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_text_with_alt(element):
    """
    BeautifulSoup要素からテキストを抽出する際、
    <img>タグをそのalt属性（アイコンの意味）に置き換え、
    <br>タグをスペースに置き換える
    """
    if not element:
        return ""
    
    # 元の要素を破壊しないようにコピーを作成
    elem_copy = copy.copy(element)
    
    # imgタグをaltテキストに置換 (例: <img alt="打"> -> "打")
    for img in elem_copy.find_all('img'):
        alt_text = img.get('alt', '')
        img.replace_with(alt_text)
        
    # brタグをスペースに置換
    for br in elem_copy.find_all('br'):
        br.replace_with(' ')

    # テキスト抽出
    return clean_text(elem_copy.get_text(strip=True))

def get_all_series_list():
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
                # シリーズ名もクリーニングする
                name = get_text_with_alt(opt)
                if val and val.isdigit():
                    series_options.append({'code': val, 'name': name})
        
        return series_options
    except Exception as e:
        print(f"Error fetching series list: {e}")
        return []

def fetch_and_parse_cards(series_code):
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
            
            card_id = clean_text(spans[0].get_text(strip=True))
            rarity = clean_text(spans[1].get_text(strip=True))
            card_type = clean_text(spans[2].get_text(strip=True))
            
            # カード名
            card_name_div = modal.find('dt').find('div', class_='cardName')
            card_name = get_text_with_alt(card_name_div)
            
            # --- 詳細情報の取得 ---
            back_col = modal.find('dd').find('div', class_='backCol')
            
            # コスト / ライフ (レイアウト通りに分割)
            cost_life_div = back_col.find('div', class_='cost')
            cost_life_type = ""
            cost_life_value = ""
            if cost_life_div:
                div_copy = copy.copy(cost_life_div)
                h3_tag = div_copy.find('h3')
                if h3_tag:
                    cost_life_type = clean_text(h3_tag.get_text(strip=True))
                    h3_tag.decompose() # h3タグを削除
                    cost_life_value = get_text_with_alt(div_copy)
                else:
                    cost_life_value = get_text_with_alt(div_copy)

            # ヘルパー関数: 特定クラスのdivから見出しを除去してテキスト化
            def get_value_cleaned(class_name, label_text):
                div = back_col.find('div', class_=class_name)
                if not div:
                    return ""
                
                # 画像(alt)やbrタグの処理のためコピー
                div_copy = copy.copy(div)
                
                # 見出し(h3)があれば削除
                h3 = div_copy.find('h3')
                if h3:
                    h3.decompose()
                    # h3を削除できたなら、テキスト抽出して終了（replaceはしない）
                    return get_text_with_alt(div_copy)
                else:
                    # h3がない場合は、テキスト抽出後にラベルを削除（念のため）
                    text = get_text_with_alt(div_copy)
                    return text.replace(label_text, '')

            attribute = get_value_cleaned('attribute', '属性')
            power = get_value_cleaned('power', 'パワー')
            counter = get_value_cleaned('counter', 'カウンター')
            color = get_value_cleaned('color', '色')
            feature = get_value_cleaned('feature', '特徴')
            block = get_value_cleaned('block', 'ブロックアイコン') # ブロックアイコン
            text = get_value_cleaned('text', 'テキスト')
            trigger = get_value_cleaned('trigger', 'トリガー')
            set_info = get_value_cleaned('getInfo', '入手情報')

            row = {
                'CardID': card_id,
                'Name': card_name,
                'Rarity': rarity,
                'Type': card_type,
                'Color': color,
                'Cost_Life_Type': cost_life_type,
                'Cost_Life_Value': cost_life_value,
                'Power': power,
                'Counter': counter,
                'Attribute': attribute,
                'Feature': feature,
                'Block': block,
                'Text': text,
                'Trigger': trigger,
                'SetInfo': set_info,
                'ImageFileID': '',
                'ImageFileID_small': ''
            }
            data.append(row)
            
        except Exception as e:
            print(f"Skipping a card in {series_code}: {e}")
            continue

    return pd.DataFrame(data)

def process_duplicates(df):
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

    series_list = get_all_series_list()
    if not series_list:
        print("No series found. Exiting.")
        return

    print(f"Found {len(series_list)} series.")

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
            df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"  -> Saved {len(df)} cards to {file_path}")
        else:
            print(f"  -> No data found for {code}")
        
        time.sleep(2)

    print("Merging all data...")
    all_files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    
    if all_files:
        df_list = [pd.read_csv(f) for f in all_files]
        df_all = pd.concat(df_list, ignore_index=True)
        
        # 全データの文字クリーニングを念のため再実行
        for col in df_all.columns:
             df_all[col] = df_all[col].apply(clean_text)

        df_final = process_duplicates(df_all)
        
        df_final['IsDuplicate'] = df_final['IsDuplicate'].apply(lambda x: '重複' if x else '')

        column_mapping = {
            'CardID': 'カード番号',
            'Name': 'カード名',
            'Rarity': 'レアリティ',
            'Type': '種類',
            'Color': '色',
            'Cost_Life_Type': 'コスト/ライフ種別',
            'Cost_Life_Value': 'コスト/ライフ値',
            'Power': 'パワー',
            'Counter': 'カウンター',
            'Attribute': '属性',
            'Feature': '特徴',
            'Block': 'ブロック',
            'Text': '効果テキスト',
            'Trigger': 'トリガー',
            'SetInfo': '入手情報',
            'IsDuplicate': '重複フラグ',
            'ImageFileID': 'ImageFileID',
            'ImageFileID_small': 'ImageFileID_small'
        }

        df_final.rename(columns=column_mapping, inplace=True)
        
        output_columns = [
            'カード番号', 'カード名', 'レアリティ', '種類', '色', 
            'コスト/ライフ種別', 'コスト/ライフ値', 'パワー', 'カウンター', '属性', 
            '特徴', 'ブロック', '効果テキスト', 'トリガー', '入手情報', 
            '重複フラグ', 'ImageFileID', 'ImageFileID_small'
        ]
        
        # 不足しているカラムがあれば追加（エラー回避）
        for col in output_columns:
            if col not in df_final.columns:
                df_final[col] = ''

        df_final = df_final[output_columns]
        
        df_final.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"Done! Total {len(df_final)} cards saved to {OUTPUT_FILE}")
    else:
        print("No data files to merge.")

if __name__ == "__main__":
    main()