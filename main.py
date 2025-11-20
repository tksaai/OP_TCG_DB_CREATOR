import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

def fetch_and_parse_cards(url):
    # サイトへの負荷を考慮し、User-Agentを設定
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # エラーがあれば例外を発生
        html_content = response.text
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return pd.DataFrame()

    soup = BeautifulSoup(html_content, 'html.parser')
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
            
            # コスト / ライフ
            cost_life_div = back_col.find('div', class_='cost')
            cost_life_val = cost_life_div.get_text(strip=True).split('</h3>')[-1]
            life = cost_life_val if 'ライフ' in cost_life_div.text else ""
            cost = cost_life_val if 'コスト' in cost_life_div.text else ""

            # 属性
            attribute_div = back_col.find('div', class_='attribute')
            attribute_img = attribute_div.find('img')
            attribute = attribute_img.get('alt', '') if attribute_img else attribute_div.get_text(strip=True).replace('属性', '')
            
            # その他の項目
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
                'Life': life,
                'Cost': cost,
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
            print(f"Skipping a card due to error: {e}")
            continue

    return pd.DataFrame(data)

def process_duplicates(df):
    # 重複処理ロジック（前回と同じ）
    # SPを含まない(0)を優先、SPを含む(1)を後にする
    df['SortPriority'] = df['Rarity'].apply(lambda x: 1 if 'SP' in x else 0)
    
    # IDと優先度でソート
    df_sorted = df.sort_values(by=['CardID', 'SortPriority']).reset_index(drop=True)
    
    # 重複フラグ作成（最初の1つ＝通常版以外はTrue）
    df_sorted['IsDuplicate'] = df_sorted.duplicated(subset=['CardID'], keep='first')
    
    return df_sorted.drop(columns=['SortPriority'])

if __name__ == "__main__":
    # 対象のURL (必要に応じてループ処理に変更してください)
    target_url = 'https://www.onepiece-cardgame.com/cardlist/?series=550113'
    
    print("Fetching data...")
    df = fetch_and_parse_cards(target_url)
    
    if not df.empty:
        print("Processing duplicates...")
        df_final = process_duplicates(df)
        
        # CSVとして保存
        df_final.to_csv('OnePiece_Card_List.csv', index=False, encoding='utf-8-sig')
        print("Done. Saved to OnePiece_Card_List.csv")
    else:
        print("No data found.")