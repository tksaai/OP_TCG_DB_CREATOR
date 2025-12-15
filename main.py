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
PROMPT_DIR = 'prompts'
OUTPUT_CSV = 'OnePiece_Card_List_All.csv'
OUTPUT_JSON = 'cards.json'
FURIGANA_DICT_FILE = 'furigana_dictionary.json'
VERIFIED_FILE = 'verified_cards.json'       # 【完了】Proモデルチェック済み
UNVERIFIED_FILE = 'unverified_cards.json'   # 【未完】処理待ちキュー
ALWAYS_FETCH_CODES = ['550901', '550801'] 

# 1回の実行でProモデル処理を行うカード数の上限
MAX_VERIFY_PER_RUN = 50 

# 校正優先キーワード
REFINE_KEYWORDS = [
    "ゴムゴム", "火拳", "神避", "芳香脚", "悪魔風脚", "大秘宝", "超新星", 
    "王下七武海", "海賊団", "一味", "拳銃", "業火", "龍", "覇気", "獅子"
]

# 環境変数からAPIキー取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- API設定とモデル確認 ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

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

# --- ヘルパー関数 ---
def load_prompt_template(filename):
    path = os.path.join(PROMPT_DIR, filename)
    if not os.path.exists(path):
        print(f"Error: Prompt file not found at {path}")
        return ""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def load_json_list(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except: return set()
    return set()

def save_json_list(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(list(data), f, ensure_ascii=False, indent=2)

def load_furigana_dict():
    if os.path.exists(FURIGANA_DICT_FILE):
        try:
            with open(FURIGANA_DICT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_furigana_dict(data):
    with open(FURIGANA_DICT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
            if not card_modals: break

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
                        'CardID': card_id, 'Name': card_name, 'Rarity': rarity, 'Type': card_type,
                        'Color': color, 'Cost_Life_Type': cost_life_type, 'Cost_Life_Value': cost_life_value,
                        'Power': power, 'Counter': counter, 'Attribute': attribute, 'Feature': feature,
                        'Block': block, 'Text': text, 'Trigger': trigger, 'SetInfo': set_info,
                        'ImageFileID': image_file_id, 'ImageFileID_small': ''
                    }
                    all_cards.append(row)
                except Exception as e:
                    print(f"Skipping card parse error: {e}")
                    continue
            
            pager = soup.find('div', class_='pager')
            if pager and 'NEXT' in pager.get_text():
                page += 1
                time.sleep(1)
            else: has_next = False
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            has_next = False
    return pd.DataFrame(all_cards)

# --- 未チェックリストの同期 ---
def sync_unverified_list(all_card_names):
    """
    全カードの中で「チェック済み(Verified)」に含まれていないものを
    すべて「未処理(Unverified)」キューに追加する
    """
    verified_set = load_json_list(VERIFIED_FILE)
    unverified_set = load_json_list(UNVERIFIED_FILE)
    
    new_cards = []
    for name in all_card_names:
        # 名前があり、かつチェック済みリストになく、まだキューにもない場合
        if name and name not in verified_set and name not in unverified_set:
            new_cards.append(name)
            
    if new_cards:
        unverified_set.update(new_cards)
        save_json_list(UNVERIFIED_FILE, unverified_set)
        print(f"Synced queue: Added {len(new_cards)} new cards to unverified list.")
    else:
        print("Queue sync: No new cards found.")

# --- フリガナのクリーニング関数 ---
def normalize_furigana(reading):
    """
    フリガナから記号やスペースを除去し、正規化する。
    ただし中黒(・)は残す。
    """
    if not reading: return ""
    # 空白、全角空白、記号（中黒以外）を除去
    # ここでは英数字、ひらがな、カタカナ、漢字、中黒以外を削除対象とする例
    # 必要に応じて調整してください。今回は「記号やスペースは除外」に従い、
    # 英数字・かな・カナ・漢字・中黒(・)を残す方針にします。
    
    # 制御文字や空白を削除
    cleaned = re.sub(r'[\s\u3000]', '', reading)
    
    # 特定の記号を削除 (例: !, ?, %, など。中黒は残す)
    # \w は英数字+アンダースコア。日本語文字も含めるため、否定で削除する文字を指定したほうが安全かもしれません。
    # ここではシンプルに「スペースと一般的な記号」を削除します。
    cleaned = re.sub(r'[!！?？"”#＃$＄%％&＆\'’(（)）*＊+＋,，-－.．/／:：;；<＜=＝>＞@＠[［\\￥\]］^＾_＿`｀{｛|｜}｝~～]', '', cleaned)
    
    return cleaned

# --- フリガナのチェック関数 ---
def is_valid_furigana(reading):
    """
    フリガナが「すべてカタカナと・」または「すべて平仮名と・」のみで構成されているかチェック
    """
    if not reading: return False
    
    # カタカナと中黒のみ
    is_katakana = re.fullmatch(r'[ァ-ヶー・]+', reading)
    if is_katakana: return True
    
    # 平仮名と中黒のみ
    is_hiragana = re.fullmatch(r'[ぁ-んー・]+', reading)
    if is_hiragana: return True
    
    return False

# --- Proモデルによるフリガナ生成関数 ---
def generate_furigana_with_pro(current_dict):
    """
    未処理リスト(UNVERIFIED_FILE)から少しずつカードを取り出し、
    Proモデルでフリガナを生成して辞書に登録する。
    """
    if not GEMINI_API_KEY: 
        print("Warning: GEMINI_API_KEY not set. Skipping AI generation.")
        return current_dict

    genai.configure(api_key=GEMINI_API_KEY)
    
    # 精度重視のモデル順
    pro_models = ['gemini-3-pro-preview', 'gemini-2.5-pro', 'gemini-1.5-pro']
    
    # 新規生成用のプロンプトを使う
    prompt_template = load_prompt_template('generation_prompt.txt')
    if not prompt_template: 
        print("Error: generation_prompt.txt missing.")
        return current_dict

    # 1. 未処理リストの読み込み
    unverified_set = load_json_list(UNVERIFIED_FILE)
    verified_set = load_json_list(VERIFIED_FILE) # チェック済みリストも読み込む
    
    if not unverified_set:
        print("Unverified queue is empty. All cards are up to date!")
        return current_dict

    # 2. 優先度付け (辞書にないもの、キーワード入りを先に)
    unverified_list = list(unverified_set)
    
    # 事前チェック: 既にきれいなフリガナがあるものはスキップして完了済みに移動
    to_verify_now = []
    to_process_ai = []
    
    for name in unverified_list:
        reading = current_dict.get(name, "")
        cleaned_reading = normalize_furigana(reading)
        
        # フリガナを正規化して更新（もし変わっていれば）
        if reading != cleaned_reading:
            current_dict[name] = cleaned_reading
            
        # チェック: カタカナのみ or 平仮名のみならAI処理スキップ
        if is_valid_furigana(cleaned_reading):
            to_verify_now.append(name)
        else:
            to_process_ai.append(name)
            
    # チェック済みを一括移動
    if to_verify_now:
        print(f"Skipping AI for {len(to_verify_now)} cards (valid format). Moving to verified...")
        verified_set.update(to_verify_now)
        save_json_list(VERIFIED_FILE, verified_set)
        
        # 未処理リストから削除
        new_unverified = set(unverified_list) - set(to_verify_now)
        save_json_list(UNVERIFIED_FILE, new_unverified)
        
        # リストを更新して続行
        unverified_list = list(new_unverified)

    if not unverified_list:
        print("All cards in queue were valid. No AI processing needed.")
        return current_dict

    def get_priority(name):
        score = 0
        current_reading = current_dict.get(name, "")
        
        # 辞書にまだない(完全新規) -> 最優先
        if name not in current_dict: 
            score += 20
        # 既に辞書にあるが、フリガナに漢字が含まれている(生成失敗の可能性) -> 優先
        elif re.search(r'[一-龥]', current_reading):
            score += 10
            
        # 難読キーワードが含まれる -> 優先
        if any(k in name for k in REFINE_KEYWORDS): 
            score += 5
            
        return -score

    unverified_list.sort(key=get_priority)

    # 3. 今回処理する分だけ切り出す
    targets_list = unverified_list[:MAX_VERIFY_PER_RUN]
    
    print(f"Processing {len(targets_list)} cards with Pro model (Remaining in queue: {len(unverified_list) - len(targets_list)})...")
    
    # 4. バッチ処理
    # Proモデルのトークン制限を考慮し、少なめのバッチサイズで回す
    batch_size = 10 
    processed_keys = [] 
    generated_updates = {}

    for i in range(0, len(targets_list), batch_size):
        batch_keys = targets_list[i:i+batch_size]
        print(f"  AI Generation batch {i+1}/{len(targets_list)}...")

        # プロンプトの構築
        prompt = prompt_template.replace("{{JSON_DATA}}", json.dumps(batch_keys, ensure_ascii=False))
        
        batch_success = False
        for model_name in pro_models:
            try:
                model = genai.GenerativeModel(model_name)
                # 創造性より正確性を重視
                response = model.generate_content(prompt, generation_config={"temperature": 0.1})
                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if match:
                    updates = json.loads(match.group(0))
                    if updates:
                        # 生成されたフリガナもクリーニングしてから登録
                        cleaned_updates = {k: normalize_furigana(v) for k, v in updates.items()}
                        generated_updates.update(cleaned_updates)
                    batch_success = True
                    break
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "quota" in err_msg.lower():
                    print(f"    Rate limit on {model_name}. Waiting 20s...")
                    time.sleep(20) 
                elif "404" in err_msg: continue
                else: print(f"    Error with {model_name}: {err_msg.splitlines()[0]}")
        
        if batch_success:
            # 成功したら、レスポンスに含まれていなくても処理済みとみなす(エラーで止まらないように)
            processed_keys.extend(batch_keys)
        else:
            print(f"    Batch failed. Skipping these cards for now.")
        
        time.sleep(10) # インターバル

    # 5. 結果の保存
    if generated_updates:
        current_dict.update(generated_updates)
        print(f"Successfully generated/updated {len(generated_updates)} readings.")
    
    if processed_keys:
        # チェック済みリストに追加
        verified_set = load_json_list(VERIFIED_FILE)
        verified_set.update(processed_keys)
        save_json_list(VERIFIED_FILE, verified_set)
        
        # 未処理リストから削除
        # 注意: unverified_list は途中で更新されている可能性があるので、ファイルを再読み込みして削除するのが安全だが
        # ここでは単純にメモリ上のリストから削除して保存
        current_unverified = load_json_list(UNVERIFIED_FILE)
        new_unverified = current_unverified - set(processed_keys)
        save_json_list(UNVERIFIED_FILE, new_unverified)
        
        print(f"Verification progress: {len(processed_keys)} cards moved to verified list.")
    
    return current_dict

# --- JSON生成 ---
def generate_card_json_from_df(df):
    cards_list = []
    seen_ids = set()
    for _, row in df.iterrows():
        if row.get('重複フラグ') == '重複': continue
        c_num = str(row['カード番号']).strip()
        if not c_num: continue
        
        img_id = str(row.get('ImageFileID', '')).strip()
        unique_suffix = img_id if img_id else str(uuid.uuid4())
        unique_id = f"{c_num}_{unique_suffix}"
        if unique_id in seen_ids: continue
        seen_ids.add(unique_id)

        info = str(row['入手情報']).strip()
        s_title = info; s_code = ''
        m = re.search(r'(.*)【(.*)】', info)
        if m: s_title = m.group(1).strip(); s_code = m.group(2).strip()

        def to_int(v):
            try: return None if not v or str(v).lower() == 'nan' else int(float(v))
            except: return str(v)

        card_obj = {
            "uniqueId": unique_id, "cardNumber": c_num, "cardName": str(row['カード名']).strip(),
            "furigana": str(row.get('フリガナ', '')).strip(), "rarity": str(row['レアリティ']).strip(),
            "cardType": str(row['種類']).strip(), "color": [c.strip() for c in str(row['色']).split('/') if c.strip()],
            "costLifeType": str(row['コスト/ライフ種別']).strip(), "costLifeValue": to_int(row['コスト/ライフ値']),
            "power": to_int(row['パワー']), "counter": to_int(row['カウンター']),
            "attribute": str(row['属性']).strip(), "features": [f.strip() for f in str(row['特徴']).split('/') if f.strip()],
            "block": to_int(row['ブロック']), "effectText": str(row['効果テキスト']).strip(),
            "trigger": str(row['トリガー']).strip(), "getInfo": info, "seriesTitle": s_title, "seriesCode": s_code
        }
        cards_list.append(card_obj)
    return cards_list

# --- メイン処理 ---
def main():
    if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
    if not os.path.exists(PROMPT_DIR): print(f"Warning: '{PROMPT_DIR}' missing.")

    series_list = get_all_series_list()
    print(f"Found {len(series_list)} series.")

    # 1. データ収集
    for s in series_list:
        code = s['code']; name = s['name']
        fpath = os.path.join(DATA_DIR, f"{code}.csv")
        if code not in ALWAYS_FETCH_CODES and os.path.exists(fpath):
            print(f"[Skip] {name}"); continue
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
        'CardID': 'カード番号', 'Name': 'カード名', 'Rarity': 'レアリティ', 'Type': '種類', 'Color': '色',
        'Cost_Life_Type': 'コスト/ライフ種別', 'Cost_Life_Value': 'コスト/ライフ値', 'Power': 'パワー',
        'Counter': 'カウンター', 'Attribute': '属性', 'Feature': '特徴', 'Block': 'ブロック',
        'Text': '効果テキスト', 'Trigger': 'トリガー', 'SetInfo': '入手情報',
        'ImageFileID': 'ImageFileID', 'ImageFileID_small': 'ImageFileID_small'
    }
    df_all.rename(columns=col_map, inplace=True)

    # 3. 未処理リストの同期 (ここで新規カードをキューに追加)
    print("Syncing processing queue...")
    sync_unverified_list(df_all['カード名'].unique())

    # 4. Proモデルによるフリガナ生成 & 校正 (キューから少しずつ消化)
    print("Generating Furigana with Pro Model...")
    f_dict = load_furigana_dict()
    f_dict = generate_furigana_with_pro(f_dict)
    save_furigana_dict(f_dict)

    # 5. フリガナ適用
    # DataFrame適用時にもクリーニングを実施
    df_all['フリガナ'] = df_all['カード名'].map(f_dict).fillna('')
    df_all['フリガナ'] = df_all['フリガナ'].apply(normalize_furigana)
    
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

    # JSON生成
    print("Generating JSON...")
    json_data = generate_card_json_from_df(df_final)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON: {OUTPUT_JSON}")

if __name__ == "__main__":
    main()