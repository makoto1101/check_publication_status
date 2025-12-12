import streamlit as st
import pandas as pd
import numpy as np
import re
from io import BytesIO
from datetime import datetime
import os
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- ステータス計算ロジックをインポート ---
from status import calculate_status
# --- 操作マニュアルをインポート ---
from operation_manual import show_instructions
# --- ステータス判定条件をインポート ---
from status_manual import show_status_conditions

# 基準日のデフォルト値とダウンロードファイル名用の日付を定義
TODAY = datetime.now().date()
TODAY_STR = TODAY.strftime('%Y%m%d')

def local_css(file_name):
    """外部CSSファイルを読み込むための関数"""
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"CSSファイル '{file_name}' が見つかりません。Pythonスクリプトと同じディレクトリに配置してください。")

# --- ページ設定 (ワイドモード) ---
st.set_page_config(layout="wide", page_title="掲載状況確認アプリ", page_icon="📊")

# --- ページ上部の余白をなくすCSSとタイトルをログイン状態に関わらず表示 ---
st.markdown("""
    <style>
            .block-container {
                padding-top: 1rem;
            }
            /* サイドバーの幅を600pxに指定 */
            [data-testid="stSidebar"] {
                width: 600px !important;
            }
    </style>
""", unsafe_allow_html=True)

# CSSの適用
local_css("style.css")

# UIレイアウト
st.title("📊 掲載状況確認アプリ")
# --------------------------------------------------------------------

# --- Streamlit 組み込み認証 ---

# 1. 未ログインの場合: ログインボタンを表示
if not st.user.get("is_logged_in", False):
    
    # カラムを使って中央に配置
    _, form_col, _ = st.columns([1.5, 1, 1.5])
    with form_col:
        # 上部に30pxの余白を追加
        st.markdown("<div style='margin-top: 80px;'></div>", unsafe_allow_html=True)
        
        st.warning('Googleアカウントでログインしてください。')
        
        # 1. まずStreamlitのボタンを表示する
        if st.button("Googleアカウントでログイン", icon=":material/login:", width='stretch'):
            # 2. ボタンが押されたら、st.login() を呼び出す（認証プロセスを開始）
            st.login() 
    
    # 未ログイン時はここでスクリプトの実行を停止する
    st.stop()

# 2. ログイン済みの場合: メインアプリを表示
else:
    # --- ヘッダーエリア（マニュアル・ステータス条件・ユーザー名・ログアウト） ---
    # レイアウト調整: [操作マニュアル] [判定条件] [空白] [ユーザー名] [ログアウト]
    # カラム比率を調整してボタンを並べる
    col_manual, col_status_link, _, col_user, col_logout = st.columns([2, 2.5, 3, 4.5, 2.2], gap="small")
    
    # 1. 操作マニュアル（リンク風ボタン）
    with col_manual:
        st.markdown("<div style='margin-top: 15px;'>", unsafe_allow_html=True)
        if st.button("📖 操作マニュアル", type="tertiary"):
            show_instructions()
        st.markdown("</div>", unsafe_allow_html=True)

    # 2. ステータス判定条件（リンク風ボタン）(★追加)
    with col_status_link:
        st.markdown("<div style='margin-top: 15px;'>", unsafe_allow_html=True)
        if st.button("📋 ステータス判定条件", type="tertiary"):
            show_status_conditions()
        st.markdown("</div>", unsafe_allow_html=True)

    # 3. ユーザー名表示
    with col_user:
        # ユーザー名は st.user.name で取得可能
        st.markdown(f"<div style='text-align: right; margin-top: 22px;'>ようこそ <b>{st.user.name}</b> さん</div>", unsafe_allow_html=True)
    
    # 4. ログアウトボタン
    with col_logout:
        st.markdown("<div style='margin-top: 0px;'>", unsafe_allow_html=True)
        if st.button("ログアウト", width='stretch'):
            st.logout()
        st.markdown("</div>", unsafe_allow_html=True)
    # ----------------------------------------------------

    # UI（st.sidebar）より先に、必要な関数や変数を定義する

    # --- Google スプレッドシート設定 ---
    GSHEET_KEY = "1Yb-0DLDb-IAKIxDkhaSZxDl-zd2iDHZ3aX3_4mSiQyI"

    # --- Google スプレッドシート連携関数 ---
    @st.cache_resource(ttl=600) # 10分間 service クライアントをキャッシュ
    def init_sheets_service():
        """Google Sheets API サービスを初期化する"""
        try:
            # st.secretsから認証情報を読み込む
            google_credentials_info = json.loads(st.secrets["gcp_service_account"]["credentials_json"])
            
            # App 2 と同じ 'readonly' スコープを使用
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets.readonly'
                # 'drive' スコープはシートの読み取りだけなら不要
            ]
            
            credentials = service_account.Credentials.from_service_account_info(
                google_credentials_info,
                scopes=scopes
            )
            
            service = build('sheets', 'v4', credentials=credentials)
            return service

        except KeyError:
            st.error("Google認証情報が見つかりません。`.streamlit/secrets.toml` に `[google]` セクションと `credentials_json` キーがあるか確認してください。")
            return None
        except json.JSONDecodeError:
            st.error("Google認証情報の形式が正しくありません。`.streamlit/secrets.toml` の `credentials_json` が有効なJSON文字列か確認してください。")
            return None
        except Exception as e:
            st.error(f"[init_sheets_service] Google Sheets サービスへの認証に失敗しました: {e}")
            st.error("`.streamlit/secrets.toml` の設定が正しいか、GCPのサービスアカウントが有効か確認してください。")
            return None
    
    def get_data_from_gsheet(_sheets_service, sheet_name, expected_headers):
        """指定されたシートからデータを読み込みDataFrameとして返す (googleapiclient版)"""
        try:
            # シート全体 (A1から最後まで) を取得する
            range_name = f"{sheet_name}!A1:ZZ" # 念のためZZ列まで
            
            result = _sheets_service.spreadsheets().values().get(
                spreadsheetId=GSHEET_KEY, 
                range=range_name
            ).execute()
            
            data = result.get('values', [])
            # ★ gspread と同じ 
            
            if not data:
                st.error(f"スプレッドシート '{sheet_name}' からデータを取得できませんでした（シートが空のようです）。")
                return pd.DataFrame(columns=expected_headers)

            headers = data[0]
            # 必要な列だけを抽出
            cols_to_use = []
            col_indices = []

            for header in expected_headers:
                try:
                    idx = headers.index(header)
                    cols_to_use.append(header)
                    col_indices.append(idx)
                except ValueError:
                    st.error(f"スプレッドシート '{sheet_name}' に必要なヘッダー '{header}' が見つかりません。")
                    return pd.DataFrame(columns=expected_headers)

            # 2行目以降のデータを取得
            records = [
                tuple(row[i] for i in col_indices if i < len(row)) # ★ 行末超えエラーを防止
                for row in data[1:]
            ]
            
            df = pd.DataFrame(records, columns=cols_to_use)
            return df

        except HttpError as err:
            # HttpError をキャッチ
            if err.resp.status == 404:
                st.error(f"スプレッドシート '{sheet_name}' が見つかりません。")
            elif err.resp.status == 403:
                st.error(f"スプレッドシート '{sheet_name}' へのアクセス権限がありません。サービスアカウントが共有されているか確認してください。")
            else:
                st.error(f"[get_data_from_gsheet] スプレッドシート '{sheet_name}' の読み込み中に HttpError が発生しました: {err}")
            return pd.DataFrame(columns=expected_headers)
        except Exception as e:
            st.error(f"[get_data_from_gsheet] スプレッドシート '{sheet_name}' の読み込み中に予期せぬエラーが発生しました: {e}")
            return pd.DataFrame(columns=expected_headers)

    # --- 各DB用データ取得関数 (Googleスプレッドシート版) ---
    @st.cache_data(ttl=600) # 10分間データをキャッシュ
    def get_teiki_data_from_gsheet(_sheets_service):
        """Googleスプレッドシートから定期便番号のセットを取得する"""
        if _sheets_service is None: return None
        
        sheet_name = "定期便DB"
        expected_headers = ["定期便番号"]
        df = get_data_from_gsheet(_sheets_service, sheet_name, expected_headers)
        
        if df.empty:
            return set() # 空のセットを返す
            
        return set(df["定期便番号"].dropna().unique())

    @st.cache_data(ttl=600)
    def get_business_data_from_gsheet(_sheets_service):
        """Googleスプレッドシートから事業者データをDataFrameとして取得する"""
        if _sheets_service is None: return pd.DataFrame(columns=["事業者コード", "事業者名", "自治体名"])
        
        sheet_name = "事業者DB"
        expected_headers = ["事業者コード", "事業者名", "自治体名"]
        df = get_data_from_gsheet(_sheets_service, sheet_name, expected_headers)
        return df

    # gspreadクライアントを初期化 -> sheetsサービスを初期化
    sheets_service = init_sheets_service()

    # 返礼品「コード」列の定義（チョイス系はインデックス番号、他はヘッダー名）
    # ユーザー指定のヘッダー名リストに基づき定義
    KEY_COLUMN_MAP = {
        # (ヘッダーなし: インデックス番号)
        "チョイス": 102,
        "チョイス在庫": 0,
        
        # (ヘッダーあり: ヘッダー名)
        "楽天": "商品番号",
        "ANA": "返礼品識別コード",
        "ふるなび": "外部返礼品コード", # 既存ロジック(index 19)とヘッダーリストを照合
        "JAL": "返礼品番号",
        "まいふる": "返礼品番号",
        "マイナビ": "返礼品番号",
        "プレミアム": "SKU", # 既存ロジック(index 5)とヘッダーリストを照合
        "JRE": "品番1", # 既存ロジック(index 2)とヘッダーリストを照合
        "さとふる": "お礼品名", # 既存ロジック(index 1, [code]抽出)とヘッダーリストを照合
        "さとふる在庫": "お礼品ID", # 既存ロジック(index 1)とヘッダーリストを照合
        "Amazon": "出品者SKU", # 既存ロジック(index 0)とヘッダーリストを照合
        "百選": "返礼品コード",
        "百選在庫": "返礼品コード",
        "ぐるなび": "商品番号"
    }

    # 返礼品「名称」列の定義（チョイス系はインデックス番号、他はヘッダー名）
    PORTAL_NAME_COLUMN_MAP = {
        # (ヘッダーなし: インデックス番号)
        "チョイス": 2,
        
        # (ヘッダーあり: ヘッダー名)
        "楽天": "商品名",
        "ANA": "返礼品名",
        "ふるなび": "返礼品名",
        "JAL": "返礼品名",
        "まいふる": "返礼品名",
        "マイナビ": "返礼品名",
        "プレミアム": "返礼品名",
        "JRE": "商品名",
        "さとふる": "お礼品名", # 既存ロジック(index 1)とヘッダーリストを照合
        "Amazon": None,
        "百選": "返礼品名称",
        "ぐるなび": "商品名"
    }

    PORTAL_ORDER = ['チョイス', '楽天', 'ANA', 'ふるなび', 'JAL', 'まいふる', 'マイナビ', 'プレミアム', 'JRE', 'さとふる', 'Amazon', '百選', 'ぐるなび']
    # TODAY_STR は L23 で定義

    # フィルタリングをスキップするシートのリスト
    SKIP_FILTERING_SHEETS = ['楽天', 'チョイス在庫', 'さとふる在庫', '百選在庫'] # 「楽天」がファイル構成が特殊なのでスキップ
    
    # ヘッダーを持たない（`header=None`で読み込む）シートのリスト
    SHEETS_WITHOUT_HEADER = ['チョイス', 'チョイス在庫']


    # --- ヘルパー関数 ---
    def get_sheet_name_from_filename(filename):
        """ファイル名からシート名を推測する"""
        name_lower = filename.lower()
        if 'チョイス在庫' in name_lower: return 'チョイス在庫'
        if 'チョイス' in name_lower: return 'チョイス'
        if '楽天' in name_lower: return '楽天'
        if 'ana' in name_lower: return 'ANA'
        if 'ふるなび' in name_lower: return 'ふるなび'
        if 'jal' in name_lower: return 'JAL'
        if 'まいふる' in name_lower: return 'まいふる'
        if 'マイナビ' in name_lower: return 'マイナビ'
        if 'プレミアム' in name_lower: return 'プレミアム'
        if 'jre' in name_lower: return 'JRE'
        if 'さとふる在庫' in name_lower: return 'さとふる在庫'
        if 'さとふる' in name_lower: return 'さとふる'
        if 'amazon' in name_lower: return 'Amazon'
        if '百選在庫' in name_lower: return '百選在庫'
        if '百選' in name_lower: return '百選'
        if 'ぐるなび' in name_lower: return 'ぐるなび'
        
        # ポータル名を特定できない場合は None を返す（インポート対象外）
        return None

    def robust_read_file(uploaded_file):
        """
        様々なエンコーディングと形式に対応したファイル読み込み関数。
        シート名に応じてヘッダーの有無（header=0 or header=None）を切り替える。
        """
        bytes_data = uploaded_file.getvalue()
        file_name = uploaded_file.name
        sheet_name = get_sheet_name_from_filename(file_name)
        
        # シート名に基づいてヘッダーの有無を決定
        # チョイス系は header=None、それ以外は header=0 (1行目をヘッダーとする)
        header_setting = None if sheet_name in SHEETS_WITHOUT_HEADER else 0

        if file_name.endswith('.xlsx'):
            try:
                return pd.read_excel(BytesIO(bytes_data), header=header_setting, dtype=str).fillna('')
            except Exception as e:
                st.error(f"Excelファイル '{file_name}' の読み込みに失敗: {e}")
                return None

        separator = '\t' if file_name.lower().endswith(('.tsv', '.txt')) else ','
        
        if '楽天' in file_name.lower() or 'さとふる' in file_name.lower():
            encodings_to_try = ['shift_jis', 'utf-8']
        elif any(n.lower() in file_name.lower() for n in ["N2", "チョイス", "プレミアム", "amazon"]):
            encodings_to_try = ['utf-8', 'shift_jis']
        else:
            encodings_to_try = ['shift_jis', 'utf-8']

        for encoding in encodings_to_try:
            try:
                corrected_encoding = 'utf-8-sig' if encoding == 'utf-8' else encoding
                df = pd.read_csv(
                    BytesIO(bytes_data), 
                    header=header_setting,
                    encoding=corrected_encoding, 
                    dtype=str, 
                    sep=separator, 
                    # engine='python',  <-- ★削除（高速化のためCエンジンを使用）
                    on_bad_lines='warn', 
                    encoding_errors='ignore'
                )
                return df.fillna('')
            except Exception:
                bytes_data = uploaded_file.getvalue()
                continue
                
        st.error(f"'{file_name}' をサポートされているエンコーディングで読み込めませんでした。ファイルが破損している可能性があります。")
        return None

    def generate_vendor_code(item_code):
        """返礼品コードから事業者コードを生成する"""
        code = str(item_code).strip()
        if not code: return ''
        if re.match(r'^\d{2}[A-Z]{4}', code): return code[:6]
        if re.match(r'^[A-Z]{4}', code): return code[:4]
        if re.match(r'^[A-Z]{3}', code): return code[:3]
        return ''

    def filter_dataframe(df, sheet_name, item_codes_to_filter, vendor_codes_to_filter):
        """
        DataFrameを指定されたコードリストでフィルタリングする関数。
        楽天の場合は「商品番号」または「システム連携用SKU番号」を対象とする。
        返礼品コード、事業者コード共に「部分一致（含む）」で判定する。
        """
        if df is None or df.empty:
            return df
        if not item_codes_to_filter and not vendor_codes_to_filter:
            return df
        
        data = df # robust_read_file でヘッダー処理済みのため、df全体がデータ
        if data.empty:
            return df

        # ★ 返礼品コード検索用の正規表現パターンを作成 (部分一致用)
        item_pattern = ""
        if item_codes_to_filter:
            item_pattern = '|'.join(map(re.escape, item_codes_to_filter))

        # ★ 事業者コード検索用の正規表現パターンを作成 (部分一致用)
        vendor_pattern = ""
        if vendor_codes_to_filter:
            vendor_pattern = '|'.join(map(re.escape, vendor_codes_to_filter))

        # --- 楽天の場合の特例処理 ---
        if sheet_name == '楽天':
            # 必要な列の存在確認 (robust_read_file後のため通常はあるはずだが安全のためget)
            col_item_no = "商品番号"
            col_sys_sku = "システム連携用SKU番号"
            
            # 列が存在しない場合はフィルタリングせずに返す（またはエラー扱いでもよいが、ここでは安全策）
            if col_item_no not in data.columns:
                st.error(f"ファイル '{sheet_name}' に '{col_item_no}' 列が見つかりません。")
                return df
            
            # 比較用にシリーズを取得 (システム連携用SKU番号がない場合も考慮してget)
            series_item_no = data[col_item_no].astype(str).str.strip()
            if col_sys_sku in data.columns:
                series_sys_sku = data[col_sys_sku].astype(str).str.strip()
            else:
                # 列がない場合はマッチしないダミーデータとして空文字シリーズを作成
                series_sys_sku = pd.Series('', index=data.index)

            # フィルタリング用のマスクを初期化 (すべてTrue)
            mask = pd.Series(True, index=data.index)

            # 1. 返礼品コードでフィルタリング (部分一致: 商品番号 OR システム連携用SKU番号)
            if item_pattern:
                # 商品番号が含まれる OR システム連携用SKU番号が含まれる (大文字小文字無視)
                match_item = series_item_no.str.contains(item_pattern, na=False, case=False)
                match_sku = series_sys_sku.str.contains(item_pattern, na=False, case=False)
                mask &= (match_item | match_sku)

            # 2. 事業者コードでフィルタリング (部分一致: 商品番号由来 OR システム連携用SKU番号由来)
            if vendor_pattern:
                # それぞれから事業者コードを生成
                vendor_series_item = series_item_no.apply(generate_vendor_code)
                vendor_series_sku = series_sys_sku.apply(generate_vendor_code)
                
                # 正規表現で部分一致検索 (大文字小文字無視)
                match_vendor_item = vendor_series_item.str.contains(vendor_pattern, na=False, case=False)
                match_vendor_sku = vendor_series_sku.str.contains(vendor_pattern, na=False, case=False)
                
                mask &= (match_vendor_item | match_vendor_sku)

            return data[mask]

        # --- 以下、既存の他ポータル用ロジック ---
        
        key_col = KEY_COLUMN_MAP.get(sheet_name)
        if key_col is None:
            # キー列が未定義ならフィルタリングしない
            return df
        
        item_code_series = pd.Series(dtype=str)
        
        # --- キー列の型（int or str）で処理を分岐 ---
        if isinstance(key_col, int):
            # (チョイス系: ヘッダーなし、インデックス番号で参照)
            if df.shape[1] <= key_col:
                st.error(f"ファイル '{sheet_name}' の列数が不足しています。キー列 {key_col} が存在しません。")
                return df
            
            # チョイス系はそのままの値を使用
            item_code_series = data.iloc[:, key_col].astype(str).str.strip()

        elif isinstance(key_col, str):
            # (その他: ヘッダーあり、ヘッダー名で参照)
            if key_col not in data.columns:
                st.error(f"ファイル '{sheet_name}' に必要なヘッダー '{key_col}' が見つかりません。")
                return df
            
            # さとふるの場合、正規表現でコードを抽出
            if sheet_name == 'さとふる':
                # 'お礼品名' 列(key_col)からコードを抽出 [xxxx] -> xxxx
                item_code_series = data[key_col].astype(str).str.extract(r'\[(.*?)\]', expand=False).fillna('')
            else:
                # 他ポータルはそのままの値を使用
                item_code_series = data[key_col].astype(str).str.strip()
        
        else:
            # key_col が None または予期せぬ型
            return df

        # フィルタリング用のマスクを初期化
        mask = pd.Series(True, index=data.index)
        
        # 1. 返礼品コードでフィルタリング (部分一致)
        if item_pattern:
            # 正規表現で部分一致検索 (大文字小文字無視)
            mask &= (item_code_series != '') & (item_code_series.str.contains(item_pattern, na=False, case=False))
        
        # 2. 事業者コードでフィルタリング (部分一致)
        if vendor_pattern:
            # 抽出または取得した返礼品コードシリーズから事業者コードを生成
            vendor_code_series = item_code_series.apply(generate_vendor_code)
            # 正規表現で部分一致検索 (大文字小文字無視)
            mask &= (vendor_code_series != '') & (vendor_code_series.str.contains(vendor_pattern, na=False, case=False))
        
        # ヘッダーは robust_read_file で処理済み (df.columns に格納)
        # そのため、データ行 (data) のみをフィルタリングして返す
        return data[mask]

    # セッションステートの初期化 (メインアプリ用)
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0
    if 'dataframes' not in st.session_state:
        st.session_state.dataframes = {}
    if 'results_df' not in st.session_state:
        st.session_state.results_df = pd.DataFrame()
    # (認証関連のセッションステートはStreamlitが内部で管理するため不要)

    # --- フィルター状態の初期化 (★ 追加: リセットされないようにsession_stateで管理) ---
    if 'f_search' not in st.session_state: st.session_state.f_search = ""
    if 'f_vendor' not in st.session_state: st.session_state.f_vendor = "すべて"
    if 'f_check' not in st.session_state: st.session_state.f_check = "すべて"
    if 'f_teiki' not in st.session_state: st.session_state.f_teiki = "すべて"

    # --- ページネーション用のセッションステート ---
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 1
    # ----------------------------------------

    # サイドバーUIセクション
    with st.sidebar:
        st.markdown('<h2 style="font-size: 24px;">1. データベース管理</h2>', unsafe_allow_html=True)

        with st.expander("DB（スプレッドシート）を開く"):
            st.markdown(
                "[「定期便番号」「事業者」の登録はこちらから](https://docs.google.com/spreadsheets/d/1Yb-0DLDb-IAKIxDkhaSZxDl-zd2iDHZ3aX3_4mSiQyI/)",
                unsafe_allow_html=True
            )
            st.info("データ編集後は、アプリを再起動 or 画面更新（「F5」キー）をしてください。")

        st.markdown('<h2 style="font-size: 24px;">2. インポート</h2>', unsafe_allow_html=True)

        with st.expander("フィルター設定を開く"):
            st.info("""
                こちらに対象のコードを入力することで、読み込むデータを絞り込むことができます。
                ※「楽天」「チョイス在庫」「さとふる在庫」「百選在庫」は仕様上、このフィルターの対象外です。
            """)
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                item_codes_to_filter_input = st.text_area(
                    "返礼品コード（改行区切りで入力）",
                    height=150,
                    key="filter_item_codes"
                )
            with filter_col2:
                vendor_codes_to_filter_input = st.text_area(
                    label="事業者コード（改行区切りで入力）", # labelを短縮
                    height=150,
                    key="filter_vendor_codes",
                    help="※アルファベット3文字 or アルファベット4文字 or 数字2文字+アルファベット4文字（計6文字）" # help引数に説明を追加
                )

        # --- ファイルアップローダー ---
        uploaded_files = st.file_uploader(
            "ファイル名に「ポータル名」を含めたファイルをアップロードしてください。\n\n(複数選択可)",
            help="※「チョイス」と「チョイス在庫」、「さとふる」と「さとふる在庫」は、それぞれ必ずセットでアップロードしてください。",
            type=['csv', 'tsv', 'xlsx', 'txt'],
            accept_multiple_files=True,
            key=f"portal_uploader_{st.session_state.uploader_key}"
        )

        # アップロードされたファイルのペア存在チェック
        if uploaded_files:
            uploaded_file_names = {get_sheet_name_from_filename(f.name) for f in uploaded_files}

            # チョイスファイルのペアチェック
            is_choice_present = 'チョイス' in uploaded_file_names
            is_choice_stock_present = 'チョイス在庫' in uploaded_file_names
            if is_choice_present ^ is_choice_stock_present:
                st.error("⚠️ 「チョイス」と「チョイス在庫」は、必ずセットでアップロードしてください。")

            # さとふるファイルのペアチェック
            is_sato_present = 'さとふる' in uploaded_file_names
            is_sato_stock_present = 'さとふる在庫' in uploaded_file_names
            if is_sato_present ^ is_sato_stock_present:
                st.error("⚠️ 「さとふる」と「さとふる在庫」は、必ずセットでアップロードしてください。")

            # 百選ファイルのペアチェック
            is_hyakusen_present = '百選' in uploaded_file_names
            is_hyakusen_stock_present = '百選在庫' in uploaded_file_names
            if is_hyakusen_present ^ is_hyakusen_stock_present:
                st.error("⚠️ 「百選」と「百選在庫」は、必ずセットでアップロードしてください。")

        def show_file_preview(uploaded_file, df_preview, num_rows=5):
            """アップロードされたファイルのプレビューを表示する"""
            with st.expander(f"📄 **{uploaded_file.name}**"):
                st.dataframe(df_preview.head(num_rows))

        all_uploaded_files = uploaded_files or []

        files_to_process = []   # 処理対象のファイルリスト

        # --- ファイル読み込みと前処理のロジック ---
        # ファイルがアップロードされたら、すぐに読み込んで前処理を行う
        if any(all_uploaded_files):

            # 1. ポータル名の重複チェック & ポータル名特定チェック (事前チェック)
            portal_to_file_map = {} # キー: sheet_name, 値: file.name
            files_to_reject_duplicate = []    # 重複拒否対象
            files_to_reject_unknown = []      # 特定不可拒否対象

            for file in all_uploaded_files:
                if file: # ファイルがNoneでないことを確認
                    sheet_name = get_sheet_name_from_filename(file.name)
                    
                    # ポータル名特定不可の場合
                    if sheet_name is None:
                         files_to_reject_unknown.append(file.name)
                         continue # 以降の処理をスキップ

                    if sheet_name in portal_to_file_map:
                        # 重複検出: このファイルは拒否リストへ
                        original_file_name = portal_to_file_map[sheet_name]
                        files_to_reject_duplicate.append((file.name, sheet_name, original_file_name))
                    else:
                        # 新規ポータル: 処理対象リストに追加
                        portal_to_file_map[sheet_name] = file.name
                        files_to_process.append(file)

            # 2. エラーメッセージの表示
            
            # (A) 特定できなかったファイルのエラー
            if files_to_reject_unknown:
                error_msg = "⚠️ **以下のファイルはポータル名を特定できなかったため、インポートされませんでした。**\n\n"
                error_msg += "ファイル名に正しいポータル名（例: 楽天, チョイス, etc.）が含まれているか確認してください。\n"
                for f_name in files_to_reject_unknown:
                    error_msg += f"- {f_name}\n"
                st.error(error_msg)

            # (B) 重複したファイルのエラー
            if files_to_reject_duplicate:
                for file_name, portal_name, original_file_name in files_to_reject_duplicate:
                    st.error(f"⚠️ **{file_name}** はインポートされませんでした。**'{portal_name}'** ポータルは既に **{original_file_name}** によって使用されています。")

            # ★ トースト表示用のフラグを初期化
            new_file_processed = False

            item_codes_list = [code.strip() for code in item_codes_to_filter_input.split('\n') if code.strip()]
            vendor_codes_list = [code.strip() for code in vendor_codes_to_filter_input.split('\n') if code.strip()]

            # 3. 処理対象のファイル (files_to_process) のみループ処理
            for file in files_to_process:
            
                # fileがNoneの可能性は事前チェックで排除されている
                sheet_name = get_sheet_name_from_filename(file.name)
                
                # ★ 変更: file_id の代わりに、名前、サイズ、タイプでファイルの一意性を判断
                file_key = f"{sheet_name}_metadata"
                current_metadata = (file.name, file.size, file.type)

                # 既に読み込まれていて、ファイルメタデータが変わっていない場合は再読み込みしない
                # ★ 変更: file_id の比較をメタデータの比較に変更
                if sheet_name not in st.session_state.dataframes or st.session_state.dataframes.get(file_key) != current_metadata:
                    df = robust_read_file(file)
                    
                    if df is not None:
                        # --- 英語版Amazonのヘッダー対応 ---
                        if sheet_name == 'Amazon':
                            # 英語版の小文字ヘッダーを日本語ヘッダーに置換
                            amazon_rename_map = {
                                'sku': '出品者SKU',
                                'asin': 'ASIN',
                                'price': '価格',
                                'quantity': '数量'
                            }
                            # リネーム実行（列が存在しない場合は何もしない）
                            df = df.rename(columns=amazon_rename_map)

                        # --- 楽天の処理 (必須列チェック & データ加工) ---
                        if sheet_name == '楽天':
                            # 1. 必須列チェック
                            required_columns = {
                                "商品管理番号（商品URL）", "商品番号", "商品名", "倉庫指定",
                                "サーチ表示", "販売期間指定（開始日時）", "販売期間指定（終了日時）",
                                "注文ボタン", "SKU管理番号", "システム連携用SKU番号",
                                "在庫数", "SKU倉庫指定"
                            }
                            missing_cols = required_columns - set(df.columns)
                            if missing_cols:
                                st.error(f"⚠️ **{file.name}** はインポートできませんでした。以下の必須列が不足しています: {', '.join(missing_cols)}")
                                continue  # このファイルの処理をスキップして次のファイルへ
                            
                            # 2. データ加工: 「システム連携用SKU番号」に値がある場合のみ、「商品番号」にコピー
                            # (空文字でない場合のみ上書きする)
                            mask_sku = df['システム連携用SKU番号'] != ''
                            df.loc[mask_sku, '商品番号'] = df.loc[mask_sku, 'システム連携用SKU番号']

                            # 3. データ加工: 「SKU倉庫指定」に値がある場合のみ、「倉庫指定」にコピー
                            # (空文字でない場合のみ上書きする)
                            mask_warehouse = df['SKU倉庫指定'] != ''
                            df.loc[mask_warehouse, '倉庫指定'] = df.loc[mask_warehouse, 'SKU倉庫指定']

                            # 4. データ加工: 先頭行のデータを同グループの下行へコピー (groupby + transform first)
                            fill_targets = ['商品名', 'サーチ表示', '販売期間指定（開始日時）', '販売期間指定（終了日時）', '注文ボタン']
                            
                            # ★高速化: groupby().transform('first') の代わりに map を使用
                            # 商品管理番号でグループ化し、各ターゲット列について、グループ内の先頭の値を全体に適用する
                            # reset_index等は不要、Seriesとして取得
                            grouped_first = df.groupby('商品管理番号（商品URL）')[fill_targets].first()
                            
                            for col in fill_targets:
                                # マッピング実行 (transformより圧倒的に速い)
                                df[col] = df['商品管理番号（商品URL）'].map(grouped_first[col])
                        # -----------------------------------

                        if sheet_name not in SKIP_FILTERING_SHEETS:
                            df = filter_dataframe(df, sheet_name, item_codes_list, vendor_codes_list)
                        
                        st.session_state.dataframes[sheet_name] = df
                        st.session_state.dataframes[file_key] = current_metadata # メタデータを保存

                        new_file_processed = True # ★ 新規ファイル処理フラグを立てる

                        # 前処理フラグのリセット
                        if sheet_name == 'チョイス在庫': st.session_state['choice_stock_processed'] = False

            # --- チョイス在庫データの前処理 ---
            # チョイスとチョイス在庫の両方が読み込まれていて、まだ前処理がされていない場合
            if "チョイス" in st.session_state.dataframes and "チョイス在庫" in st.session_state.dataframes:
                if not st.session_state.get('choice_stock_processed', False):
                    df_choice = st.session_state.dataframes["チョイス"]
                    df_choice_stock = st.session_state.dataframes["チョイス在庫"].copy()
                    # データフレームに必要な列が存在するか確認
                    # (チョイス: index 1, 102), (チョイス在庫: index 1)
                    if df_choice.shape[1] > 102 and df_choice_stock.shape[1] > 1:
                        # チョイスデータから 商品管理番号(1) と 返礼品コード(102) を抽出
                        df_map_source = df_choice[[1, 102]].dropna().copy()
                        # 文字列型にして前後の空白を除去
                        df_map_source[1] = df_map_source[1].astype(str).str.strip()
                        df_map_source[102] = df_map_source[102].astype(str).str.strip()
                        # 商品管理番号で重複を除去 (最初の一つを残す)
                        df_map_source = df_map_source.drop_duplicates(subset=[1], keep='first')
                        # 商品管理番号をキー、返礼品コードを値とする辞書を作成
                        id_map = df_map_source.set_index(1)[102].to_dict()
                        # チョイス在庫の 商品管理番号(1) 列を取得し、文字列型に変換
                        lookup_keys = df_choice_stock[1].astype(str).str.strip()
                        # map関数を使って返礼品コードを紐付け
                        mapped_codes = lookup_keys.map(id_map)
                        # 紐付けた返礼品コードを先頭列(0列目)に挿入
                        df_choice_stock.insert(0, 'generated_code', mapped_codes)
                        # 列名をリセット (0, 1, 2, ...)
                        df_choice_stock.columns = range(df_choice_stock.shape[1])
                        # 処理済みのデータフレームをセッションステートに保存
                        st.session_state.dataframes["チョイス在庫"] = df_choice_stock
                        # 前処理済みフラグを立てる
                        st.session_state['choice_stock_processed'] = True

                        # ★ 在庫処理も新規処理とみなす
                        if not new_file_processed: # 重複トーストを避ける
                            new_file_processed = True

            # 新規ファイルの処理が完了した場合にトーストを表示
            if new_file_processed:
                st.toast("インポートが完了しました。", icon="📄")

        # --- インポートされたファイルのプレビュー Expander ---
        # session_state.dataframes にファイルID以外のキーが存在するか確認
        # _id -> _metadata
        processed_dataframes_exist = any(not k.endswith('_metadata') for k in st.session_state.dataframes)

        # 処理済みのデータフレームが存在する場合のみ Expander を表示
        if processed_dataframes_exist:
            with st.expander("インポートされたファイルのプレビュー", expanded=False):
                col_idx = 0
                processed_files_count = 0 # 正常に処理されたファイルの数をカウント
                for file in files_to_process:
                    if file:
                        sheet_name = get_sheet_name_from_filename(file.name)
                        # 前処理の結果、データフレームが存在するか確認
                        if sheet_name in st.session_state.dataframes:
                            show_file_preview(file, st.session_state.dataframes[sheet_name])
                            processed_files_count += 1
                # もしアップロードファイルはあるのに、処理されたものがなければメッセージ表示
                if processed_files_count == 0 and any(all_uploaded_files):
                    st.write("ファイルの読み込み/処理に失敗したため、プレビューできません。")
                elif processed_files_count == 0: # アップロードファイルもない場合
                    st.write("ファイルがアップロードされていません。")

        st.markdown('<h2 style="font-size: 24px;">3. 実行</h2>', unsafe_allow_html=True)

        # ベースポータル選択機能
        st.markdown('<p style="font-size: 14px; margin-top: 10px; margin-bottom: 5px;">選択されたポータルと基準日を元に掲載状況を表示します。</p>', unsafe_allow_html=True)

        # インポートされたポータル名のリストを取得
        # _id -> _metadata
        uploaded_portal_names = [p for p in PORTAL_ORDER if p in st.session_state.dataframes and not p.endswith('_metadata')]

        # ファイルがアップロードされているかどうかのフラグ
        files_uploaded = bool(uploaded_portal_names)
        
        # ベースポータルと日付選択をカラムで横並びにする
        col1, col2 = st.columns([2, 1]) # 2:1 の比率

        with col1:
            if files_uploaded:
                # 「チョイス」があればデフォルトにするためのインデックスを計算
                default_index = 0
                if "チョイス" in uploaded_portal_names:
                    default_index = uploaded_portal_names.index("チョイス")

                selected_base_portal = st.selectbox(
                    label="ベースポータル選択",
                    options=uploaded_portal_names,
                    index=default_index, # デフォルト選択を設定
                    label_visibility="collapsed"
                )
            else:
                selected_base_portal = None
                st.selectbox(
                    label="ベースポータル選択",
                    options=["ファイルをアップロードしてください"],
                    disabled=True,
                    label_visibility="collapsed"
                )

        # 日付選択ウィジェット (カレンダー)
        with col2:
            selected_date = st.date_input(
                label="基準日", # ラベルは非表示
                value=TODAY, # L22 で定義した本日日付
                disabled=not files_uploaded,
                label_visibility="collapsed",
                help="ステータス判定の基準となる日付を選択します。"
            )

        # --- 「掲載状況を表示」ボタン ---
        st.markdown('<div class="button-container" style="margin-top: 10px;">', unsafe_allow_html=True)
        
        # ★ 実行中フラグの初期化
        if 'is_running' not in st.session_state:
            st.session_state.is_running = False

        # ★ ボタンクリック時のコールバック関数
        def start_processing():
            st.session_state.is_running = True

        run_button = st.button(
            "掲載状況を表示",
            key="sidebar_run_button",
            disabled=not files_uploaded or st.session_state.is_running, # ★ ファイル未選択 または 実行中は無効化
            on_click=start_processing # ★ クリック時に処理開始フラグを立てる
        )
        st.markdown('</div>', unsafe_allow_html=True)


    # --- メインページUIセクション ---
    # ボタンの戻り値ではなく、セッションステートのフラグで判定
    if st.session_state.is_running:
        # スプレッドシートクライアントが正常かチェック
        if sheets_service is None:
            st.error("Googleスプレッドシートに接続できません。認証設定を確認してください。")
            st.session_state.is_running = False # 停止する前にフラグを戻す
            st.stop()
            
        # 処理実行前のバリデーションチェック
        # _id -> _metadata
        loaded_df_names = {k for k in st.session_state.dataframes if not k.endswith('_metadata')}
        
        # ベースポータルが選択されているか
        if selected_base_portal is None:
            st.error("ファイルがアップロードされていないため、ベースポータルを選択できません。")

        # さとふるファイルのペア存在チェック
        is_sato_present = 'さとふる' in loaded_df_names
        is_sato_stock_present = 'さとふる在庫' in loaded_df_names
        satofuru_files_ok = not (is_sato_present ^ is_sato_stock_present)
        if not satofuru_files_ok:
            st.error("「さとふる」と「さとふる在庫」は両方同時にインポートする必要があります。ファイル選択を確認してください。")

        # 百選ファイルのペア存在チェック
        is_hyakusen_present = '百選' in loaded_df_names
        is_hyakusen_stock_present = '百選在庫' in loaded_df_names
        hyakusen_files_ok = not (is_hyakusen_present ^ is_hyakusen_stock_present)
        if not hyakusen_files_ok:
             st.error("「百選」と「百選在庫」は両方同時にインポートする必要があります。ファイル選択を確認してください。")

        # ベースポータルがNoneでないことと、さとふる・百選ファイルがOKなことを確認
        if selected_base_portal and satofuru_files_ok and hyakusen_files_ok:
            
            # 選択された日付を 'YYYYMMDD' 形式の文字列に変換
            select_date_str = selected_date.strftime('%Y%m%d')
            
            # ★ 追加: セッションステートに基準日とベースポータルを保存
            st.session_state.current_select_date_str = select_date_str
            st.session_state.current_base_portal = selected_base_portal

            with st.spinner("データを処理し、ステータスを計算中..."):
                try:
                    teiki_bin_codes = get_teiki_data_from_gsheet(sheets_service)
                    if teiki_bin_codes is None: # 取得失敗
                        st.error("定期便DB（スプレッドシート）の読み込みに失敗しました。")
                        st.session_state.is_running = False # ★ 停止する前にフラグを戻す
                        st.stop()
                    
                    # ★ 商品管理DBの読み込みを削除
                    
                    df_business = get_business_data_from_gsheet(sheets_service)
                    if df_business is None: # 取得失敗
                        st.error("事業者DB（スプレッドシート）の読み込みに失敗しました。")
                        st.session_state.is_running = False # ★ 停止する前にフラグを戻す
                        st.stop()
                    # ---------------------------------

                    # ★ 変更: _id -> _metadata
                    full_data = {k: v for k, v in st.session_state.dataframes.items() if not k.endswith('_metadata')}
                    
                    master_items = {}
                    base_portal_name = selected_base_portal
                    df_base = full_data.get(base_portal_name)
                    
                    # ベースポータルから返礼品コードと名称のリストを作成
                    df_base_data = df_base # robust_read_fileでヘッダー処理済み
                    
                    if df_base_data is not None:
                        code_col = KEY_COLUMN_MAP.get(base_portal_name)
                        name_col = PORTAL_NAME_COLUMN_MAP.get(base_portal_name)

                        if code_col is not None:
                            # gspread と googleapiclient で .dropna() の挙動が異なる可能性があるため
                            # キー列が存在することを確認してから subset を指定する
                            subset_col = [code_col] if code_col in df_base_data.columns or isinstance(code_col, int) else None
                            if subset_col:
                                df_master_source = df_base_data.dropna(subset=subset_col).copy()
                            else:
                                df_master_source = df_base_data.copy() # subset なし (万が一の場合)

                            
                            # --- キー列の型（int or str）で処理を分岐 ---
                            if isinstance(code_col, int):
                                # (チョイス系: インデックス番号で参照)
                                # (lookup_maps側とクレンジング処理を合わせる)
                                # ★ 変更: すべて .str.upper() に統一
                                df_master_source['key'] = df_master_source[code_col].astype(str).str.replace('\ufeff', '', regex=False).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
                            
                            elif isinstance(code_col, str):
                                # (その他: ヘッダー名で参照)
                                if base_portal_name == 'さとふる':
                                    # ★ 変更: すべて .str.upper() に統一
                                    df_master_source['key'] = df_master_source[code_col].astype(str).str.extract(r'\[(.*?)\]', expand=False).fillna('').str.upper()
                                else:
                                    # ★ 変更: すべて .str.upper() に統一
                                    df_master_source['key'] = df_master_source[code_col].astype(str).str.replace('\ufeff', '', regex=False).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
                            # 重複を除去
                            unique_items = df_master_source[df_master_source['key'] != ''].drop_duplicates(subset=['key'], keep='first')

                            # マスター辞書を作成
                            for _, row in unique_items.iterrows():
                                item_code = row['key']
                                item_name = ""
                                if name_col is not None:
                                    try:
                                        item_name = str(row[name_col]).strip()
                                    except KeyError:
                                        item_name = ""
                                master_items[item_code] = item_name
                        
                    lookup_maps, parent_lookup_maps = {}, {}

                    # --- 楽天ステータス判定用のデータ準備 ---
                    # ★ 商品管理DB廃止に伴い、memo_map も廃止（空辞書とする）
                    memo_map = {}

                    # 楽天データから各種対応辞書を作成 (ヘッダー名で参照)
                    rakuten_product_id_map = {} # 商品番号 -> 行データ
                    rakuten_management_id_map = {} # 商品管理番号（商品URL） -> 行データ
                    rakuten_sku_code_map = {} # SKU管理番号 -> 行データ
                    
                    # ★ 【追加】楽天のグループマップ作成 (商品管理番号 -> 行リスト)
                    rakuten_group_map = {}

                    if '楽天' in full_data:
                        df_rakuten = full_data['楽天']
                        # robust_read_fileでヘッダー処理済みのため、iloc[1:] は不要
                        df_rakuten_data = df_rakuten
                        
                        # ★「商品番号」列のソート -> 行データ
                        if '商品番号' in df_rakuten_data.columns:
                            # まず商品番号がある行を抽出
                            df_rakuten_b = df_rakuten_data.dropna(subset=['商品番号']).copy()
                            
                            # --- 分割ソート ---

                            # 1. SKU有無の判定（フラグ作成）
                            # 「システム連携用SKU番号」に値がある（空文字でない）場合はTrue
                            if 'システム連携用SKU番号' in df_rakuten_b.columns:
                                has_sku_mask = (df_rakuten_b['システム連携用SKU番号'].astype(str).str.strip() != '')
                            else:
                                has_sku_mask = pd.Series(False, index=df_rakuten_b.index)

                            # --- ランク計算用ロジック（全行に対して計算だけ行う） ---
                            # ※計算自体は全行に行うが、ソートに使うのはSKUありの行だけにする

                            # 日付処理用の関数
                            def _get_date_str(x):
                                s = str(x).strip()
                                return re.sub(r'[^0-9]', '', s)[:8]

                            # 列名の定義
                            col_warehouse = '倉庫指定' if '倉庫指定' in df_rakuten_b.columns else None
                            col_search = 'サーチ表示' if 'サーチ表示' in df_rakuten_b.columns else None
                            col_order = '注文ボタン' if '注文ボタン' in df_rakuten_b.columns else None
                            col_start = '販売期間指定（開始日時）' if '販売期間指定（開始日時）' in df_rakuten_b.columns else None
                            col_end = '販売期間指定（終了日時）' if '販売期間指定（終了日時）' in df_rakuten_b.columns else None
                            col_stock = '在庫数' if '在庫数' in df_rakuten_b.columns else None
                            
                            current_date_str = TODAY_STR

                            # 【1】「倉庫指定」: '0' が優先 -> 昇順
                            def _calc_warehouse_rank(x):
                                if col_warehouse and str(x).strip() == '0': return 0
                                return 1
                            df_rakuten_b['p_rank_1'] = df_rakuten_b[col_warehouse].apply(_calc_warehouse_rank) if col_warehouse else 1

                            # 【2】「サーチ表示」: '1' が優先 -> 降順
                            df_rakuten_b['p_rank_2'] = pd.to_numeric(df_rakuten_b[col_search], errors='coerce').fillna(0) if col_search else 0

                            # 【3】「注文ボタン」: '1' が優先 -> 降順
                            df_rakuten_b['p_rank_3'] = pd.to_numeric(df_rakuten_b[col_order], errors='coerce').fillna(0) if col_order else 0

                            # 【4】「開始日時」
                            s_start_dates = df_rakuten_b[col_start].apply(_get_date_str) if col_start else pd.Series('', index=df_rakuten_b.index)
                            def _calc_start_cat(d):
                                if not d: return 0      # ① 空
                                if d <= current_date_str: return 1 # ② 過去
                                return 2                # ③ 未来
                            df_rakuten_b['p_rank_4_cat'] = s_start_dates.apply(_calc_start_cat)
                            df_rakuten_b['p_rank_4_val'] = s_start_dates

                            # 【5】「終了日時」
                            s_end_dates = df_rakuten_b[col_end].apply(_get_date_str) if col_end else pd.Series('', index=df_rakuten_b.index)
                            def _calc_end_cat(d):
                                if not d: return 0      # ① 空
                                if d >= current_date_str: return 1 # ② 未来
                                return 2                # ③ 過去
                            df_rakuten_b['p_rank_5_cat'] = s_end_dates.apply(_calc_end_cat)
                            df_rakuten_b['p_rank_5_val'] = s_end_dates

                            # 【6】「在庫数」: 多い方が優先 -> 降順
                            df_rakuten_b['p_rank_6'] = pd.to_numeric(df_rakuten_b[col_stock], errors='coerce').fillna(0) if col_stock else 0

                            # --- データの分割とソート ---
                            
                            # SKUありのグループ
                            df_sku = df_rakuten_b[has_sku_mask].copy()
                            # SKUなしのグループ
                            df_no_sku = df_rakuten_b[~has_sku_mask].copy()

                            # SKUありグループのみ、優先度順にソートする
                            if not df_sku.empty:
                                sort_columns = [
                                    'p_rank_1',     # 【1】倉庫 (0優先 -> 昇順)
                                    'p_rank_2',     # 【2】サーチ (1優先 -> 降順)
                                    'p_rank_3',     # 【3】注文 (1優先 -> 降順)
                                    'p_rank_4_cat', # 【4】開始区分 (空<過去<未来 -> 昇順)
                                    'p_rank_4_val', # 【4】開始日値 (古い日付優先 -> 昇順)
                                    'p_rank_5_cat', # 【5】終了区分 (空<未来<過去 -> 昇順)
                                    'p_rank_5_val', # 【5】終了日値 (新しい日付優先 -> 降順)
                                    'p_rank_6'      # 【6】在庫 (多い順 -> 降順)
                                ]
                                asc_settings = [True, False, False, True, True, True, False, False]
                                df_sku = df_sku.sort_values(by=sort_columns, ascending=asc_settings)
                            
                            # SKUなしグループはソートしない（元のファイル順序を維持）
                            # 何もしない

                            # 結合（SKUありを上に）
                            df_rakuten_b = pd.concat([df_sku, df_no_sku])

                            # 重複排除 (keep='first'なので、SKUありが優先され、同グループ内ではソート上位/ファイル上位が残る)
                            df_rakuten_b = df_rakuten_b.drop_duplicates(subset=['商品番号'], keep='first')
                            
                            # 辞書化
                            rakuten_product_id_map = {str(row['商品番号']).strip().upper(): row.to_dict() for _, row in df_rakuten_b.iterrows()}
                        
                        # A列(商品管理番号（商品URL）) -> 行データ
                        if '商品管理番号（商品URL）' in df_rakuten_data.columns:
                            df_rakuten_a = df_rakuten_data.dropna(subset=['商品管理番号（商品URL）']).drop_duplicates(subset=['商品管理番号（商品URL）'], keep='first')
                            # ★ 変更: .upper() に統一
                            rakuten_management_id_map = {str(row['商品管理番号（商品URL）']).strip().upper(): row.to_dict() for _, row in df_rakuten_a.iterrows()}

                        # H列(SKU管理番号) -> 行データ
                        if 'SKU管理番号' in df_rakuten_data.columns:
                            df_rakuten_h = df_rakuten_data.dropna(subset=['SKU管理番号']).drop_duplicates(subset=['SKU管理番号'], keep='first')
                            # ★ 重要: SKU管理番号は厳密比較のため、.upper() しない (元のまま)
                            rakuten_sku_code_map = {str(row['SKU管理番号']).strip(): row.to_dict() for _, row in df_rakuten_h.iterrows()}
                        
                        # ★ 【追加】グループマップの構築
                        if '商品管理番号（商品URL）' in df_rakuten_data.columns:
                            for _, row in df_rakuten_data.iterrows():
                                mid = str(row['商品管理番号（商品URL）']).strip().upper()
                                if mid:
                                    if mid not in rakuten_group_map: rakuten_group_map[mid] = []
                                    rakuten_group_map[mid].append(row.to_dict())
                    
                    # --- 他ポータルのデータ準備 (lookup_maps 作成) ---
                    for name, df in full_data.items():
                        key_col = KEY_COLUMN_MAP.get(name)
                        
                        if key_col is None:
                            continue # キー列が未定義のシートはスキップ
                        
                        df_data_only = df # robust_read_fileでヘッダー処理済み
                        
                        # --- キー列の型（int or str）で処理を分岐 ---
                        if isinstance(key_col, int):
                            # (チョイス系: インデックス番号で参照)
                            if df.shape[1] <= key_col:
                                st.error(f"ファイル '{name}' の列数が不足しています。キー列 {key_col} が存在しません。")
                                continue
                                
                            df_cleaned = df_data_only.dropna(subset=[key_col]).copy()
                            # BOM等の除去、.0除去、空白除去
                            # ★ 変更: すべて .str.upper() に統一
                            df_cleaned['key_col_str'] = df_cleaned[key_col].astype(str).str.replace('\ufeff', '', regex=False).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
                            df_cleaned = df_cleaned[df_cleaned['key_col_str'] != '']
                            
                            unique_data = df_cleaned.drop_duplicates(subset=['key_col_str'], keep='first')
                            # キーがインデックス番号(0, 1...)の辞書を作成
                            lookup_maps[name] = {row['key_col_str']: row.to_dict() for _, row in unique_data.iterrows()}

                        elif isinstance(key_col, str):
                            # (その他: ヘッダー名で参照)
                            if key_col not in df.columns:
                                st.error(f"ファイル '{name}' に必要なヘッダー '{key_col}' が見つかりません。")
                                continue
                            
                            df_cleaned = df_data_only.dropna(subset=[key_col]).copy()
                            
                            if name == 'さとふる':
                                temp_map = {}
                                for _, row in df_cleaned.iterrows():
                                    # 'お礼品名' 列(key_col)からコードを抽出
                                    match = re.search(r'\[(.*?)\]', str(row.get(key_col, ''))) 
                                    if match:
                                        # ★ 変更: すべて .upper() に統一
                                        key = match.group(1).strip().upper()
                                        if key and key not in temp_map:
                                            # キーがヘッダー名('お礼品ID', 'お礼品名'...)の辞書を作成
                                            temp_map[key] = row.to_dict()
                                lookup_maps[name] = temp_map
                            else:
                                # BOM等の除去、.0除去、空白除去
                                # ★ 変更: すべて .str.upper() に統一
                                df_cleaned['key_col_str'] = df_cleaned[key_col].astype(str).str.replace('\ufeff', '', regex=False).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
                                df_cleaned = df_cleaned[df_cleaned['key_col_str'] != '']
                                
                                unique_data = df_cleaned.drop_duplicates(subset=['key_col_str'], keep='first')
                                # キーがヘッダー名('商品番号', '商品名'...)の辞書を作成
                                lookup_maps[name] = {row['key_col_str']: row.to_dict() for _, row in unique_data.iterrows()}

                    results_data = []
                    uploaded_portals = [p for p in PORTAL_ORDER if p in full_data]

                    for code, name in master_items.items():
                        statuses = {
                            portal: calculate_status(
                                portal, code, lookup_maps, parent_lookup_maps,
                                
                                # 基準日(文字列)をキーワード引数として渡す
                                select_date_str=select_date_str,
                                
                                # 楽天用の辞書をキーワード引数として渡す
                                memo_map=memo_map,
                                rakuten_product_id_map=rakuten_product_id_map,
                                rakuten_management_id_map=rakuten_management_id_map,
                                rakuten_sku_code_map=rakuten_sku_code_map,
                                # ★ 【追加】楽天のグループマップを渡す
                                rakuten_group_map=rakuten_group_map
                            ) for portal in uploaded_portals
                        }
                        
                        status_values = list(statuses.values())
                        
                        # --- チェックロジック ---
                        unique_statuses = set(status_values)
                        
                        # 「非表示」「在庫0」「受付終了」「倉庫」の4種を「グレーゾーン」と定義
                        allowed_gray_statuses = {'非表示', '在庫0', '受付終了', '倉庫'}
                        
                        # グレーゾーン以外のステータス（公開中、未登録など）を抽出
                        main_statuses = unique_statuses - allowed_gray_statuses
                        
                        # グレーゾーンのステータスを抽出
                        gray_statuses = unique_statuses.intersection(allowed_gray_statuses)
                        
                        check_val = "OK" # デフォルトをOKに設定
                        
                        # パターン1: グレーゾーン以外のステータスが2種類以上ある場合 (例: '公開中'と'未登録')
                        if len(main_statuses) >= 2:
                            check_val = "要確認"
                        
                        # パターン2: グレーゾーン以外のステータスが1種類あり、かつグレーゾーンのステータスも1種類以上ある場合 (例: '公開中'と'在庫0')
                        elif len(main_statuses) == 1 and len(gray_statuses) >= 1:
                            check_val = "要確認"
                        
                        public_count = sum(1 for s in status_values if s == '公開中')
                        
                        teiki_bin_flag = '〇' if code in teiki_bin_codes else '×'
                            
                        result_row = {'返礼品コード': code, '返礼品名': name, '事業者コード': generate_vendor_code(code), **statuses,
                                      'チェック': check_val, '定期便フラグ': teiki_bin_flag, '公開中の数': public_count}
                        results_data.append(result_row)
                    
                    if results_data:
                        df_results = pd.DataFrame(results_data)
                        
                        # df_business は Gsheetから取得済みのものを使用
                        if not df_business.empty:
                            df_business_names = df_business[['事業者コード', '事業者名']]
                            df_results = pd.merge(df_results, df_business_names, on='事業者コード', how='left')
                            df_results['事業者名'] = df_results['事業者名'].fillna('')
                        else:
                            df_results['事業者名'] = ''
                        
                        base_columns = ['返礼品コード', '返礼品名', '事業者コード', '事業者名']
                        base_portal_column_list = [base_portal_name] if base_portal_name in df_results.columns else []
                        other_portal_columns = [
                            p for p in PORTAL_ORDER 
                            if p in df_results.columns and p != base_portal_name
                        ]
                        utility_columns = ['チェック', '定期便フラグ', '公開中の数']
                        display_columns = base_columns + base_portal_column_list + other_portal_columns + utility_columns
                        final_display_columns = [col for col in display_columns if col in df_results.columns]
                        st.session_state.results_df = df_results.reindex(columns=final_display_columns)
                    else:
                        st.session_state.results_df = pd.DataFrame()
                    
                except Exception as e:
                    st.error(f"処理中に予期せぬエラーが発生しました: {e}"); import traceback; st.code(traceback.format_exc())
                    st.session_state.results_df = pd.DataFrame()

            # ★ 追加: 処理完了のトーストメッセージ
            st.toast("掲載状況の表示を更新しました。", icon="📊")
            
            # ★ 処理完了後にフラグを下ろして再実行（ボタンを有効化するため）
            st.session_state.is_running = False
            st.rerun()

        else:
            # バリデーションエラー時はフラグだけ下ろしてrerunしない（エラーメッセージを表示させたままにする）
            st.session_state.is_running = False

    st.markdown('<h2 style="font-size: 26px;">3. 掲載状況</h2>', unsafe_allow_html=True)

    # リセット完了メッセージの表示
    if 'show_reset_success' in st.session_state:
        st.toast("掲載状況をリセットしました。", icon="✅")
        del st.session_state.show_reset_success

    if st.session_state.results_df.empty:
        if run_button:
            st.warning("表示対象データがありません。")
        else:
            st.info("ファイルやDBをサイドバーから設定し、「掲載状況を表示」ボタンを押してください。")
    else:
        df_to_display = st.session_state.results_df.copy()
        
        # --- フィルターセクション ---
        filter_cols = st.columns(4)

        # ★ コールバック関数 (session_stateに保存するため)
        def update_f_search(): st.session_state.f_search = st.session_state.w_search
        def update_f_vendor(): st.session_state.f_vendor = st.session_state.w_vendor
        def update_f_check(): st.session_state.f_check = st.session_state.w_check
        def update_f_teiki(): st.session_state.f_teiki = st.session_state.w_teiki

        with filter_cols[0]:
            # 全文検索: session_state.f_search の値を使用
            st.text_input(
                "全文検索 (コード/返礼品名/事業者名):",
                value=st.session_state.f_search,
                key="w_search",
                on_change=update_f_search
            )
            # フィルタリング適用
            if st.session_state.f_search:
                search_text = st.session_state.f_search
                df_to_display = df_to_display[
                    df_to_display['返礼品コード'].str.contains(search_text, na=False, case=False) |
                    df_to_display['返礼品名'].str.contains(search_text, na=False, case=False) |
                    df_to_display['事業者名'].str.contains(search_text, na=False, case=False)
                ]

        with filter_cols[1]:
            vendor_list = sorted(st.session_state.results_df['事業者コード'].unique())
            vendor_options = ["すべて"] + vendor_list
            
            # 選択肢のインデックスを計算
            current_vendor = st.session_state.f_vendor
            v_index = vendor_options.index(current_vendor) if current_vendor in vendor_options else 0

            st.selectbox(
                "事業者コード:",
                vendor_options,
                index=v_index,
                key="w_vendor",
                on_change=update_f_vendor
            )
            # フィルタリング適用
            if st.session_state.f_vendor != "すべて":
                df_to_display = df_to_display[df_to_display['事業者コード'] == st.session_state.f_vendor]

        with filter_cols[2]:
            check_options = ["すべて", "OK", "要確認"]
            current_check = st.session_state.f_check
            c_index = check_options.index(current_check) if current_check in check_options else 0
            
            st.selectbox(
                "チェック:",
                check_options,
                index=c_index,
                key="w_check",
                on_change=update_f_check
            )
            # フィルタリング適用
            if st.session_state.f_check != "すべて":
                df_to_display = df_to_display[df_to_display['チェック'] == st.session_state.f_check]

        with filter_cols[3]:
            teiki_options = ["すべて", "〇", "×"]
            current_teiki = st.session_state.f_teiki
            t_index = teiki_options.index(current_teiki) if current_teiki in teiki_options else 0
            
            st.selectbox(
                "定期便:",
                teiki_options,
                index=t_index,
                key="w_teiki",
                on_change=update_f_teiki
            )
            # フィルタリング適用
            if st.session_state.f_teiki != "すべて":
                df_to_display = df_to_display[df_to_display['定期便フラグ'] == st.session_state.f_teiki]
        
        # --- ページネーション設定 (★ DataFrame描画前に計算処理を移動 ★) ---
        # 1ページあたりの表示件数
        ITEMS_PER_PAGE = 500 
        
        # フィルター後の総アイテム数を計算
        total_items = len(df_to_display)
        
        # フィルター結果に基づき、総ページ数と現在のページ番号を計算・補正
        if total_items > 0:
            # 総ページ数を計算
            total_pages = (total_items // ITEMS_PER_PAGE) + (1 if total_items % ITEMS_PER_PAGE > 0 else 0)
            
            # 現在のページ番号を取得
            current_page = st.session_state.current_page
            
            # フィルター適用後に total_pages が減った場合、現在のページが最大ページを超えないように補正
            if current_page > total_pages:
                st.session_state.current_page = total_pages
                current_page = total_pages # スライス処理用にローカル変数も更新
        else:
            # データが0件の場合
            total_pages = 1
            st.session_state.current_page = 1
            current_page = 1
        
        st.write("")

        # 表示件数とエクスポートボタンを横並びに配置
        count_col, _, button_col = st.columns([3, 6, 4]) 

        with count_col:
            # 読み取ったすべてのデータの件数
            total_count = len(st.session_state.results_df)
            
            # フィルターをかけた状態の件数
            filtered_count = len(df_to_display)
            
            # --- 表示形式を分岐 ---
            if total_count == filtered_count:
                # フィルターがかかっていない場合 (またはフィルター結果が総件数と一致する場合)
                display_text = f"{total_count}件 表示"
            else:
                # フィルターがかかっている場合
                display_text = f"{filtered_count} / {total_count}件 表示"

            # ★ HTML/CSSでフォントサイズを大きく (1.1rem) して表示
            st.markdown(
                f"""
                <span style='font-size: 1.1rem; font-weight: bold; white-space: nowrap;'>
                {display_text}
                </span>
                """, 
                unsafe_allow_html=True
            )

        EXCEL_COLOR_MAP = {
            # 'ステータス': (bg_color, font_color)
            '公開中': ('#22a579', '#FFFFFF'),
            '未登録': ('#111111', '#FFFFFF'),
            '受付終了': ('#6c757d', '#FFFFFF'),
            '非表示': ('#6c757d', '#FFFFFF'),
            '在庫0': ('#6c757d', '#FFFFFF'),
            '倉庫': ('#6c757d', '#FFFFFF'),
            '未受付': ('#ffc107', '#000000'), # 未受付は黒文字
            '要確認': ('#fa6c78', '#000000')  # 要確認は黒文字
        }

        # --- to_excel 関数 ---
        def to_excel(df):
            output = BytesIO()
            # XlsxWriter をエンジンとして指定
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                sheet_name = 'Sheet1'
                workbook = writer.book
                
                # --- 1. 書式(フォーマット)の定義 ---
                
                # デフォルト書式 (フォント: 游ゴシック)
                default_format = workbook.add_format({
                    'font_name': '游ゴシック'
                })

                # ヘッダー書式 (フォント: 游ゴシック, 罫線なし, 太字)
                header_format = workbook.add_format({
                    'font_name': '游ゴシック',
                    'bold': True,
                    'border': 0  # 罫線なし
                })

                # 色付きセルの書式を動的に作成
                color_formats = {}
                for status, (bg_color, font_color) in EXCEL_COLOR_MAP.items():
                    color_formats[status] = workbook.add_format({
                        'font_name': '游ゴシック',
                        'bg_color': bg_color,
                        'font_color': font_color
                    })
                
                # --- 2. DataFrameをExcelに書き込む (データのみ) ---
                # to_excelでデータのみ書き込む (ヘッダーは後で手動描画)
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
                
                # ワークシートオブジェクトを取得
                worksheet = writer.sheets[sheet_name]

                # --- 3. ヘッダーを手動で書き込む (書式適用のため) ---
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)

                # --- 4. データセルに書式を適用 ---
                # (to_excelはデフォルト書式しか適用できないため、色付けのために上書き)
                
                # PORTAL_ORDER は L.263 付近で定義済み
                portal_cols = [p for p in PORTAL_ORDER if p in df.columns]
                check_col_name = 'チェック'
                
                # データ行をイテレート
                for row_num in range(len(df)):
                    # データ行の開始は1行目 (0行目はヘッダー)
                    excel_row_idx = row_num + 1 
                    
                    # カラムをイテレート
                    for col_num, col_name in enumerate(df.columns):
                        value = df.iloc[row_num, col_num]
                        
                        # デフォルト書式をまず適用
                        cell_format = default_format
                        
                        # 色付け対象列か判定
                        if col_name in portal_cols and value in color_formats:
                            cell_format = color_formats.get(value, default_format)
                        elif col_name == check_col_name and value == '要確認':
                            cell_format = color_formats.get('要確認', default_format)
                        
                        # セルに値と書式を書き込む
                        # (to_excelで既に書かれた値を上書き)
                        worksheet.write(excel_row_idx, col_num, value, cell_format)

                # --- 5. 列幅を自動調整 ---
                # DataFrameの列名とインデックス番号の辞書を作成
                col_indices = {col_name: i for i, col_name in enumerate(df.columns)}

                # PORTAL_ORDER は L.263 付近で定義済み
                portal_cols = [p for p in PORTAL_ORDER if p in col_indices]
                utility_cols = ['チェック', '定期便フラグ', '公開中の数']

                # デフォルト幅
                default_width = 13 # (ステータス列やコードなど)

                # 列ごとに幅を設定
                for col_name, col_idx in col_indices.items():
                    width = default_width # デフォルト幅をセット
                    
                    if col_name == '返礼品名':
                        # ★ 返礼品名を 60 に設定 (現在の約2/3を想定)
                        width = 60 
                    elif col_name == '事業者名':
                        # ★ 事業者名を 25 に設定 (少し広げる)
                        width = 25 
                    elif col_name == '事業者コード':
                        width = 15 # 事業者コードは少し広め
                    elif col_name not in portal_cols and col_name not in utility_cols:
                        # ステータス列以外 (返礼品コードなど)
                        width = 15 
                    
                    # set_column(first_col, last_col, width)
                    worksheet.set_column(col_idx, col_idx, width)
                
            # writer.close() は with ブロックが自動で処理
            return output.getvalue()

        # --- CSV変換関数 ---
        @st.cache_data
        def to_csv(df):
            # DataFrameをまずCSV文字列に変換
            # (to_csvにencodingを指定しても文字列出力では無視されるため、ここでは指定しない)
            csv_string = df.to_csv(index=False) 
            
            # 文字列を cp932 バイト列にエンコード
            # ★ エンコードできない文字は '?' に置換 (errors='replace')
            return csv_string.encode('cp932', errors='replace')

        with button_col:
            if not df_to_display.empty:
                
                # ★ カラム間の隙間を "small" (セレクトボックスと同じ) に設定
                excel_col, csv_col = st.columns([1, 1], gap="small")

                # --- Excel保存ボタンを1列目に配置 ---
                with excel_col:
                    excel_data = to_excel(df_to_display)
                    
                    # ★ 変更: session_stateから値を取得
                    # L708で保存した値を使用。存在しない場合のデフォルト値も設定
                    base_portal_for_name = st.session_state.get('current_base_portal', 'N/A')
                    date_str_for_name = st.session_state.get('current_select_date_str', 'YYYYMMDD')
                    
                    # ★ 変更: ファイル名を新しい形式に
                    file_name_excel = f"掲載状況データ_{TODAY_STR}（target_{base_portal_for_name}_{date_str_for_name}）.xlsx"
                    
                    st.download_button(
                        label="Excel保存",
                        data=excel_data,
                        file_name=file_name_excel, # ★ 変更
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="excel_download",
                        width='stretch' 
                    )

                # --- CSV保存ボタンを2列目に配置 ---
                with csv_col:
                    csv_data = to_csv(df_to_display)
                    
                    # ★ 変更: session_stateから値を取得 (上記と同じ変数を使用)
                    base_portal_for_name = st.session_state.get('current_base_portal', 'N/A')
                    date_str_for_name = st.session_state.get('current_select_date_str', 'YYYYMMDD')
                    
                    # ★ 変更: ファイル名を新しい形式に
                    file_name_csv = f"掲載状況データ_{TODAY_STR}（target_{base_portal_for_name}_{date_str_for_name}）.csv"
                    
                    st.download_button(
                        label="CSV保存",
                        data=csv_data,
                        file_name=file_name_csv, # ★ 変更
                        mime="text/csv",
                        key="csv_download",
                        width='stretch'
                    )

        # --- データフレームのスタイリングと表示 ---
        color_map = {'公開中': 'background-color: #22a579; color: white;', '未登録': 'background-color: #111111; color: white;', '受付終了': 'background-color: #6c757d; color: white;', 
                     '非表示': 'background-color: #6c757d; color: white;', '在庫0': 'background-color: #6c757d; color: white;', '倉庫': 'background-color: #6c757d; color: white;',
                     '未受付': 'background-color: #ffc107; color: black;'}
        
        def style_dataframe(df):
            style = pd.DataFrame('', index=df.index, columns=df.columns)
            portal_cols = [p for p in PORTAL_ORDER if p in df.columns]
            for col in portal_cols: style[col] = df[col].map(color_map).fillna('')
            if 'チェック' in df.columns: style['チェック'] = df['チェック'].apply(lambda x: 'background-color: #fa6c78; color: black;' if x == '要確認' else '')
            return style

        # --- データのスライスと描画 ---
        
        # フィルター結果が0件でない場合のみスライスと描画を実行
        # (0件の場合は L.1138 の st.warning が表示される想定)
        if not df_to_display.empty:
        
            # ページ番号からスライスするインデックスを計算
            # (current_page は L.1193 で補正済み)
            start_idx = (current_page - 1) * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            
            # データをスライス
            df_sliced = df_to_display.iloc[start_idx:end_idx]
            
            # ★ スライスしたDFのインデックスを全体の連番に変更
            df_sliced.index = range(start_idx + 1, start_idx + 1 + len(df_sliced))
            
            # スタイリング対象のカラムリスト
            center_aligned_cols = [p for p in PORTAL_ORDER if p in df_sliced.columns] + ['チェック', '定期便フラグ', '公開中の数']

            # ★ スライスした df_sliced に対してスタイリング
            styler = df_sliced.style.apply(style_dataframe, axis=None).set_properties(subset=center_aligned_cols, **{'text-align': 'center'})

            # ★ スライスしたデータのみを描画
            st.dataframe(styler, width='stretch', height=800)

        # --- ページネーションUI (表の下に配置) ---
        # total_items, total_pages, current_page は フィルター直後(L.1184付近)で計算済み
        
        # フィルター結果が0件でない場合のみページネーションを表示
        if total_items > 0:
            # (ITEMS_PER_PAGE, total_pages, current_page は L.1184 付近で定義・計算済み)
            
            # [全件数表示] [ [n] / n ページ] 
            col_spacer, col_page_input, col_page_total, col_spacer_end, col_max_num = st.columns([
                3.5,  # 空白 (調整)
                1.0, # [n] (入力欄)
                0.9, # / n ページ (テキスト)
                1.0,  # 空白 (調整)
                1.5  # 最大件数説明文
            ])

            # ページ番号入力用のコールバック関数
            # (st.number_input の on_change で呼び出される)
            def update_page_number():
                # number_inputの値(page_input_box)をcurrent_pageに反映する
                if st.session_state.page_input_box != st.session_state.current_page:
                    st.session_state.current_page = st.session_state.page_input_box
                    # on_change が発火すると Streamlit が自動で rerun するため、st.rerun() は不要

            with col_page_input:
                # ページ番号入力欄
                st.number_input(
                    label="ページ番号",
                    min_value=1,
                    max_value=total_pages,
                    value=current_page, # ★ 表示する値は常に current_page
                    step=1,
                    key="page_input_box", # ★ key をコールバック参照用の別名に変更
                    on_change=update_page_number, # 変更時にコールバックを実行
                    label_visibility="collapsed",
                    help=f"1～{total_pages} のページ番号を入力"
                )

            with col_page_total:
                # 総ページ数表示 (左揃えにして入力欄のすぐ右に配置)
                st.markdown(
                    f"<div style='margin-top: 8px; text-align: left; font-weight: bold;'> / {total_pages} ページ</div>",
                    unsafe_allow_html=True
                )
            
            with col_max_num:
                # ページ番号表示 (中央揃え)
                st.markdown(
                    f"<div style='margin-top: 8px; text-align: center; font-weight: 500;'>※1ページ最大500件表示</div>",
                    unsafe_allow_html=True
                )

        st.markdown("---")
        
        # リセットボタンの確認ダイアログ
        if 'confirming_reset' not in st.session_state:
            st.session_state.confirming_reset = False

        if st.session_state.confirming_reset:
            st.warning("本当に掲載状況をリセットしてもよろしいですか？")
            
            col1, col2, _ = st.columns([1, 1, 8], gap="small") 
            
            with col1:
                if st.button("OK", key="reset_confirm_ok", width='stretch'):
                    # 実行処理
                    if 'dataframes' in st.session_state:
                        meta_keys = [k for k in st.session_state.dataframes if k.endswith('_metadata')]
                        for k in meta_keys:
                            del st.session_state.dataframes[k] # 辞書の中身を削除

                    keys_to_clear = [
                        'results_df', 'dataframes', 'choice_stock_processed', 'rakuten_merged',
                        'current_select_date_str', 'current_base_portal',
                        'f_search', 'f_vendor', 'f_check', 'f_teiki' # ★ フィルター設定もクリア
                    ]
                    for key in keys_to_clear:
                        if key in st.session_state:
                            del st.session_state[key] # 属性自体を削除

                    st.session_state.uploader_key += 1
                    
                    # 完了メッセージ用のフラグを立てる
                    st.session_state.show_reset_success = True
                    
                    # 状態をクリアして再描画
                    st.session_state.confirming_reset = False
                    st.rerun()
            with col2:
                if st.button("キャンセル", key="reset_confirm_cancel", width='stretch'):
                    st.session_state.confirming_reset = False
                    st.rerun()
        else:
            if st.button("掲載状況をリセット"):
                st.session_state.confirming_reset = True
                st.rerun()