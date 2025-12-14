import os
import time
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import copy
import uuid
import google.generativeai as genai
import importlib.metadata

# --- 設定 ---
BASE_URL = 'https://www.onepiece-cardgame.com/cardlist/'
DATA_DIR = 'data'
OUTPUT_CSV = 'OnePiece_Card_List_All.csv'
OUTPUT_JSON = 'cards.json'
FURIGANA_DICT_FILE = 'furigana_dictionary.json'
ALWAYS_FETCH_CODES = ['550901', '550801'] 

# 環境変数からAPIキー取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- バージョン確認 ---
try:
    genai_version = importlib.metadata.version("google-generativeai")
    print(f"google-generativeai version: {genai_version}")
except:
    pass

# --- APIキーとモデルの接続テスト (追加) ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print("Checking available models for this API key...")
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f" - Found model: {m.name}")
                available_models.append(m.name)
        
        if not available_models:
            print("WARNING: No models found! Please check 'Generative Language API' in Google Cloud Console.")
    except Exception as e:
        print(f"Error listing models: {e}")
        print("Hint: Your API Key might be invalid or lacks permissions.")

# --- テキストクリーニング関数 ---
def clean_text(text):
    if text is None: return ""
    if isinstance(text, float) and pd.isna(text): return ""
    text = str(text)
    if text.lower() == 'nan': return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_text_with_alt(element):
    if not element: return ""
    elem_copy = copy.copy(element)
    for img in elem_copy.find_all('img'):
        alt_text = img.get('alt', '')
        img.replace_with(alt_text)
    for br in elem_copy.find_all('br'):
        br.replace_with(' ')
    return clean_text(elem_copy.get_text(strip=True))

def extract_image_id(img_tag):
    if not img_tag: return ""
    src = img_tag.get('src', '')
    if not src: return ""
    filename = os.path.basename(src)
    return filename

# --- スクレイピング関連 ---
def get_all_series_list():
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; Bot/1.0)'}
    try:
        response = requests.get(BASE_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        series_options = []
        select_tag = soup.find('select', {'name': 'series'})
        if select_tag:
            options = select_tag.find_all('option')
            for opt in options:
                val = opt.get('value')
                name = get_text_with_alt(opt)
                if val and val.isdigit():
                    series_options.append({'code': val, 'name': name})
        return series_options
    except Exception as e:
        print(f"Error fetching series list: {e}")
        return []

def fetch_cards_from_series(series_code):
    all_cards = []
    page = 1
    has_next = True
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; Bot/1.0)'}

    while has_next:
        url = f"{BASE_URL}?series={series_code}&page={page}"
        print(f"  Fetching Page {page}...")
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            card_modals = soup.find_all('dl', class_='modalCol')
            if not card_modals:
                break

            for modal in card_modals:
                try:
                    dt = modal.find('dt')
                    info_col = dt.find('div', class_='infoCol')
                    spans = info_col.find_all('span')
                    
                    card_id = clean_text(spans[0].get_text(strip=True)) if len(spans) > 0 else ""
                    rarity = clean_text(spans[1].get_text(strip=True)) if len(spans) > 1 else ""
                    card_type = clean_text(spans[2].get_text(strip=True)) if len(spans) > 2 else ""
                    
                    card_name_div = dt.find('div', class_='cardName')
                    card_name = get_text_with_alt(card_name_div)
                    
                    img_tag = modal.find('img')
                    image_file_id = extract_image_id(img_tag)
                    
                    dd = modal.find('dd')
                    back_col = dd.find('div', class_='backCol')
                    
                    cost_life_div = back_col.find('div', class_='cost')
                    cost_life_type = ""
                    cost_life_value = ""
                    if cost_life_div:
                        cl_copy = copy.copy(cost_life_div)
                        h3 = cl_copy.find('h3')
                        if h3:
                            cost_life_type = clean_text(h3.get_text(strip=True))
                            h3.decompose()
                        cost_life_value = get_text_with_alt(cl_copy)

                    def get_val(cls, label):
                        div = back_col.find('div', class_=cls)
                        if not div: return ""
                        d_copy = copy.copy(div)
                        h3 = d_copy.find('h3')
                        if h3: h3.decompose()
                        return get_text_with_alt(d_copy).replace(label, '')

                    attribute = get_val('attribute', '属性')
                    power = get_val('power', 'パワー')
                    counter = get_val('counter', 'カウンター')
                    color = get_val('color', '色')
                    feature = get_val('feature', '特徴')
                    block = get_val('block', 'ブロックアイコン') 
                    text = get_val('text', 'テキスト')
                    trigger = get_val('trigger', 'トリガー')
                    set_info = get_val('getInfo', '入手情報')

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
                        'ImageFileID': image_file_id,
                        'ImageFileID_small': ''
                    }
                    all_cards.append(row)

                except Exception as e:
                    print(f"Skipping card parse error: {e}")
                    continue
            
            pager = soup.find('div', class_='pager')
            if pager and 'NEXT' in pager.get_text():
                page += 1
                time.sleep(1)
            else:
                has_next = False
                
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            has_next = False

    return pd.DataFrame(all_cards)

# --- フリガナ (Gemini API) 関連 ---
def load_furigana_dict():
    if os.path.exists(FURIGANA_DICT_FILE):
        try:
            with open(FURIGANA_DICT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_furigana_dict(data):
    with open(FURIGANA_DICT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_furigana_from_ai(card_names):
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set. Skipping AI furigana.")
        return {}

    genai.configure(api_key=GEMINI_API_KEY)
    
    # 試行するモデルリスト
    # ユーザー環境で確認された最新モデルを優先的に指定
    default_models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-flash-latest']

    # APIから取得できるモデルも動的に候補に追加
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_name = m.name.replace('models/', '')
                if model_name not in default_models:
                    default_models.append(model_name)
    except Exception as e:
        print(f"Warning: Could not auto-detect models: {e}")
    
    new_readings = {}
    # 【対策1】バッチサイズを 30 -> 10 に減らし、負荷を分散
    batch_size = 10 
    
    unique_names = list(set(card_names))
    
    for i in range(0, len(unique_names), batch_size):
        batch = unique_names[i:i+batch_size]
        print(f"Asking AI for furigana ({i+1}/{len(unique_names)})...")
        
        prompt = f"""
        あなたはワンピースカードゲームの専門家です。以下のカード名のリストについて、
        正しい「読み仮名（全角カタカナ）」を答えてください。
        「芳香脚」は「パフューム・フェムル」のように、ルビ（当て字）を優先してください。
        
        出力は以下のJSON形式のみを返してください。マークダウン記法は不要です。
        {{
            "カード名": "ヨミガナ",
            ...
        }}

        リスト:
        {json.dumps(batch, ensure_ascii=False)}
        """
        
        # 【対策2】リトライロジック強化 (Exponential Backoff)
        max_retries = 3
        retry_delay = 10 # 初回待機時間
        success = False

        for attempt in range(max_retries):
            # モデルごとの試行
            for model_name in default_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    match = re.search(r'\{.*\}', response.text, re.DOTALL)
                    if match:
                        res_json = json.loads(match.group(0))
                        new_readings.update(res_json)
                        success = True
                        break # 成功したらモデルループを抜ける
                except Exception as e:
                    err_msg = str(e)
                    # 429 (Resource Exhausted) の場合は、モデルを変えるのではなく待機が必要
                    if "429" in err_msg or "quota" in err_msg.lower():
                         print(f"Rate limit hit on {model_name}. Waiting...")
                         break # モデルループを抜けて、外側のリトライループで待機する
                    elif "404" in err_msg:
                        # モデルが見つからない場合は次のモデルへ即座に移行
                        continue
                    else:
                        print(f"Model {model_name} failed: {err_msg}")
                        continue
            
            if success:
                break
            
            # 失敗時は待機してからリトライ
            print(f"Retry {attempt + 1}/{max_retries} after {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry_delay *= 2 # 待機時間を倍にする (10s -> 20s -> 40s)

        if not success:
            print(f"All retries failed for batch starting at {i}. Skipping this batch.")

        # 【対策3】成功時の基本待機時間を 4s -> 10s に延長 (RPM制限対策)
        time.sleep(10) 

    return new_readings

# --- JSON生成 ---
def generate_card_json_from_df(df):
    cards_list = []
    seen_ids = set()

    for _, row in df.iterrows():
        if row.get('重複フラグ') == '重複':
            continue

        c_num = str(row['カード番号']).strip()
        if not c_num: continue

        img_id = str(row.get('ImageFileID', '')).strip()
        unique_suffix = img_id if img_id else str(uuid.uuid4())
        unique_id = f"{c_num}_{unique_suffix}"
        
        if unique_id in seen_ids: continue
        seen_ids.add(unique_id)

        info = str(row['入手情報']).strip()
        s_title = info
        s_code = ''
        m = re.search(r'(.*)【(.*)】', info)
        if m:
            s_title = m.group(1).strip()
            s_code = m.group(2).strip()

        def to_int(v):
            try:
                if not v or str(v).lower() == 'nan': return None
                return int(float(v))
            except: return str(v)

        card_obj = {
            "uniqueId": unique_id,
            "cardNumber": c_num,
            "cardName": str(row['カード名']).strip(),
            "furigana": str(row.get('フリガナ', '')).strip(),
            "rarity": str(row['レアリティ']).strip(),
            "cardType": str(row['種類']).strip(),
            "color": [c.strip() for c in str(row['色']).split('/') if c.strip()],
            "costLifeType": str(row['コスト/ライフ種別']).strip(),
            "costLifeValue": to_int(row['コスト/ライフ値']),
            "power": to_int(row['パワー']),
            "counter": to_int(row['カウンター']),
            "attribute": str(row['属性']).strip(),
            "features": [f.strip() for f in str(row['特徴']).split('/') if f.strip()],
            "block": to_int(row['ブロック']),
            "effectText": str(row['効果テキスト']).strip(),
            "trigger": str(row['トリガー']).strip(),
            "getInfo": info,
            "seriesTitle": s_title,
            "seriesCode": s_code
        }
        cards_list.append(card_obj)
    
    return cards_list

# --- メイン処理 ---
def main():
    if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
    
    series_list = get_all_series_list()
    print(f"Found {len(series_list)} series.")

    # 1. データ収集
    for s in series_list:
        code = s['code']
        name = s['name']
        fpath = os.path.join(DATA_DIR, f"{code}.csv")
        
        if code not in ALWAYS_FETCH_CODES and os.path.exists(fpath):
            print(f"[Skip] {name}")
            continue

        print(f"[Fetch] {name} ({code})...")
        df = fetch_cards_from_series(code)
        if not df.empty:
            df.to_csv(fpath, index=False, encoding='utf-8-sig')
            print(f"  Saved {len(df)} cards.")
        time.sleep(1)

    # 2. 統合
    print("Merging data...")
    files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    if not files: return

    df_list = [pd.read_csv(f, dtype=str) for f in files]
    df_all = pd.concat(df_list, ignore_index=True).fillna('')
    
    df_all['SortPriority'] = df_all['Rarity'].apply(lambda x: 1 if 'SP' in str(x) else 0)
    df_all = df_all.sort_values(by=['CardID', 'SortPriority']).reset_index(drop=True)
    df_all['IsDuplicate'] = df_all.duplicated(subset=['CardID'], keep='first')
    df_all['IsDuplicate'] = df_all['IsDuplicate'].apply(lambda x: '重複' if x else '')
    df_all = df_all.drop(columns=['SortPriority'])

    col_map = {
        'CardID': 'カード番号', 'Name': 'カード名', 'Rarity': 'レアリティ',
        'Type': '種類', 'Color': '色', 'Cost_Life_Type': 'コスト/ライフ種別',
        'Cost_Life_Value': 'コスト/ライフ値', 'Power': 'パワー', 'Counter': 'カウンター',
        'Attribute': '属性', 'Feature': '特徴', 'Block': 'ブロック',
        'Text': '効果テキスト', 'Trigger': 'トリガー', 'SetInfo': '入手情報',
        'ImageFileID': 'ImageFileID', 'ImageFileID_small': 'ImageFileID_small'
    }
    df_all.rename(columns=col_map, inplace=True)

    # 3. AIフリガナ付与
    print("Applying Furigana...")
    f_dict = load_furigana_dict()
    targets = [n for n in df_all['カード名'].unique() if n and n not in f_dict]
    
    if targets:
        print(f"Fetching readings for {len(targets)} new words...")
        new_f = fetch_furigana_from_ai(targets)
        f_dict.update(new_f)
        save_furigana_dict(f_dict)
    
    df_all['フリガナ'] = df_all['カード名'].map(f_dict).fillna('')
    
    # CSV保存
    cols = [
        'カード番号', 'カード名', 'フリガナ', 'レアリティ', '種類', '色', 
        'コスト/ライフ種別', 'コスト/ライフ値', 'パワー', 'カウンター', '属性', 
        '特徴', 'ブロック', '効果テキスト', 'トリガー', '入手情報', 
        '重複フラグ', 'ImageFileID', 'ImageFileID_small'
    ]
    out_cols = [c for c in cols if c in df_all.columns]
    df_final = df_all[out_cols]
    
    df_final.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"Saved CSV: {OUTPUT_CSV}")

    # 4. JSON生成
    print("Generating JSON...")
    json_data = generate_card_json_from_df(df_final)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON: {OUTPUT_JSON}")

if __name__ == "__main__":
    main()