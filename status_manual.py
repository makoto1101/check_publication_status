import streamlit as st

# --- 1. CSSクラス定義 (Python内で完結させる) ---
# ※ !important をつけて確実に適用させます
CUSTOM_CSS = """
<style>
/* ============================================
   ステータス判定表のスタイル
   ============================================ */

/* ステータスセルの共通設定 */
.status-cell {
    width: 100px;
    text-align: center;
    vertical-align: middle !important;
    font-weight: bold;
    border: 1px solid #ddd;
    padding: 10px;
    white-space: nowrap;
}

/* 各ステータスの色定義 */
.st-public    { background-color: #22a579 !important; color: #FFFFFF !important; } /* 公開中 */
.st-unreg     { background-color: #111111 !important; color: #FFFFFF !important; } /* 未登録 */
.st-closed    { background-color: #6c757d !important; color: #FFFFFF !important; } /* 受付終了 */
.st-hidden    { background-color: #6c757d !important; color: #FFFFFF !important; } /* 非表示 */
.st-stock0    { background-color: #6c757d !important; color: #FFFFFF !important; } /* 在庫0 */
.st-warehouse { background-color: #6c757d !important; color: #FFFFFF !important; } /* 倉庫 */
.st-notyet    { background-color: #ffc107 !important; color: #000000 !important; } /* 未受付 */
.st-check     { background-color: #fa6c78 !important; color: #000000 !important; } /* 要確認 */

/* 説明セルの設定 */
.desc-cell {
    padding: 10px;
    border: 1px solid #ddd;
    vertical-align: top !important;
    color: #333;
    background-color: #ffffff;
}

/* ============================================
   タブ (Tabs) のスタイル調整
   ============================================ */
/* ★変更: タブリスト（親要素）を折り返し可能にする */
div[data-baseweb="tab-list"] {
    gap: 4px !important;
    flex-wrap: wrap !important; /* 折り返しを有効化して全タブを表示 */
    margin-bottom: 10px !important;
}

/* ★変更: タブボタンのスタイル調整 */
button[data-baseweb="tab"] {
    min-width: auto !important; /* 固定最小幅を解除 */
    padding-left: 12px !important; /* 余白を調整 */
    padding-right: 12px !important;
    padding-top: 8px !important;
    padding-bottom: 8px !important;
    font-weight: bold !important;
    flex-grow: 1 !important; /* 均等に広げる */
}
</style>
"""

# --- ステータス名とCSSクラスの対応表 ---
STATUS_CLASS_MAP = {
    '公開中': 'st-public',
    '未登録': 'st-unreg',
    '受付終了': 'st-closed',
    '非表示': 'st-hidden',
    '在庫0':   'st-stock0',
    '倉庫':   'st-warehouse',
    '未受付': 'st-notyet',
    '要確認': 'st-check'
}

def create_status_row(status_label, title, description):
    """
    テーブルの1行分のHTMLを生成するヘルパー関数
    """
    # 対応するクラス名を取得（なければデフォルト）
    css_class = STATUS_CLASS_MAP.get(status_label, '')
    
    html = f"""
    <tr style="border-bottom: 1px solid #ddd;">
        <td class="status-cell {css_class}">
            {status_label}
        </td>
        <td class="desc-cell">
            <div style="font-weight: bold; color: #003366; margin-bottom: 4px;">{title}</div>
            <div style="font-size: 0.9rem; line-height: 1.4;">{description}</div>
        </td>
    </tr>
    """
    return html

def render_table(rows_html):
    """
    テーブル全体をレンダリングする関数
    """
    table_html = f"""
    <table style="width: 100%; border-collapse: collapse; font-family: '游ゴシック', sans-serif;">
        {rows_html}
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)

# --- ダイアログ（モーダルウィンドウ）の定義 ---
@st.dialog("ステータス判定条件", width="large")
def show_status_conditions():
    # ★ ここでCSSを読み込ませる
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # --- スクロールエリアの定義 ---
    with st.container(height=600, border=True):
        st.info("各ポータルのステータスは、以下の優先順位（番号順）で判定され、条件に合致した時点で確定します。")

        # ポータルごとにタブを分けて表示
        # 順番: チョイス, 楽天, JAL, ふるなび, ANA, まいふる, マイナビ, プレミアム, JRE, さとふる, Amazon, 百選
        tabs = st.tabs([
            "チョイス", "楽天", "JAL", "ふるなび", "ANA", 
            "まいふる", "マイナビ", "プレミアム", "JRE", "さとふる", "Amazon", "百選"
        ])

        # --- チョイス ---
        with tabs[0]:
            rows = ""
            rows += create_status_row("未登録", "【1】 掲載フラグ取得不可", "チョイスファイルにデータが存在しない、または「（必須）表示有無(CT列)」が空欄の場合")
            rows += create_status_row("非表示", "【2】 表示有無が 0", "「表示有無(CT列)」の値が <code>0</code> の場合")
            rows += create_status_row("在庫0", "【3】 在庫数が 0", "チョイス在庫ファイルの「残り在庫数（D列）」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【4】 受付開始・終了なし", "「受付開始日時(CU列)」と「受付終了日時(CV列)」が共に設定されていない場合")
            rows += create_status_row("未受付", "【5】 受付開始日時が未来", "「受付開始日時(CU列)」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("公開中", "【6】 受付終了日時なし", "受付開始済みで、かつ「受付終了日時(CV列)」が空欄の場合")
            rows += create_status_row("受付終了", "【7】 受付終了日時が過去", "「受付終了日時(CV列)」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【8】 上記以外", "期間内など、上記条件に該当しない場合")
            render_table(rows)

        # --- 楽天 ---
        with tabs[1]:
            rows = ""
            rows += create_status_row("未登録", "【1】 SKU親コードなし", "ファイルまたはDBから商品管理番号(SKU親)が取得できない場合")
            rows += create_status_row("在庫0", "【2】 在庫数が 0", "「在庫数」が <code>0</code> の場合")
            rows += create_status_row("倉庫", "【3】 倉庫指定あり", "SKU行または商品行の「倉庫指定」が <code>1</code> の場合")
            rows += create_status_row("非表示", "【4】 サーチ表示が 0", "「サーチ表示」が <code>0</code> の場合")
            rows += create_status_row("未受付", "【5】 注文ボタンが 0", "「注文ボタン」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【6】 販売期間設定なし", "「販売期間指定（開始日時）」と「販売期間指定（終了日時）」が共に設定されていない場合")
            rows += create_status_row("未受付", "【7】 販売開始日時が未来", "「販売期間指定（開始日時）」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【8】 販売終了日時が過去", "「販売期間指定（終了日時）」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【9】 上記以外", "期間内（販売終了日時の設定なしを含む）など、上記条件に該当しない場合")
            render_table(rows)

        # --- JAL ---
        with tabs[2]:
            rows = ""
            rows += create_status_row("未登録", "【1】 ステータス空欄", "ファイルの「ステータス」が空欄の場合")
            rows += create_status_row("受付終了", "【2】 品切れ・受付終了", "ファイルの「ステータス」が <code>品切れ</code> または <code>受付終了</code> の場合")
            rows += create_status_row("非表示", "【3】 表示設定が非表示", "ファイルの「表示設定」が <code>非表示</code> の場合")
            rows += create_status_row("在庫0", "【4】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合（※在庫設定なしを除く）")
            rows += create_status_row("未受付", "【5】 表示開始日時が未来", "「表示開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 表示終了日時が過去", "「表示終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("未受付", "【7】 寄附開始日時が未来", "「寄附開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【8】 寄附終了日時が過去", "「寄附終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【9】 上記以外", "すべての条件をクリアした場合")
            render_table(rows)

        # --- ふるなび ---
        with tabs[3]:
            rows = ""
            rows += create_status_row("未登録", "【1】 販売フラグ空欄", "ファイルの「販売フラグ」が空欄の場合")
            rows += create_status_row("非表示", "【2】 フラグが off", "「販売フラグ」または「公開フラグ」が <code>off</code> の場合")
            rows += create_status_row("在庫0", "【3】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【4】 公開期間設定なし", "「公開開始日」と「公開終了日」が共に空欄の場合")
            rows += create_status_row("未受付", "【5】 公開開始日時が未来", "「公開開始日」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 公開終了日時が過去", "「公開終了日」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【7】 上記以外", "期間内など、上記条件に該当しない場合")
            render_table(rows)

        # --- ANA ---
        with tabs[4]:
            rows = ""
            rows += create_status_row("未登録", "【1】 状態(掲載フラグ)空欄", "ファイルの「状態(掲載フラグ)」が空欄の場合")
            rows += create_status_row("非表示", "【2】 状態(掲載フラグ)が 1", "ファイルの「状態(掲載フラグ)」が <code>1</code> (非公開) の場合")
            rows += create_status_row("在庫0", "【3】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【4】 販売期間設定なし", "「販売開始日」と「販売終了日」が共に空欄の場合")
            rows += create_status_row("未受付", "【5】 販売開始日が未来", "「販売開始日」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 販売終了日が過去", "「販売終了日」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【7】 上記以外", "期間内など、上記条件に該当しない場合")
            render_table(rows)

        # --- まいふる ---
        with tabs[5]:
            rows = ""
            rows += create_status_row("未登録", "【1】 ステータス空欄", "ファイルの「ステータス」が空欄の場合")
            rows += create_status_row("受付終了", "【2】 売り切れ・受付終了", "ファイルの「ステータス」が <code>売り切れ</code> または <code>受付終了</code> の場合")
            rows += create_status_row("非表示", "【3】 状態が非表示", "ファイルの「状態」が <code>非表示</code> の場合")
            rows += create_status_row("在庫0", "【4】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合")
            rows += create_status_row("未受付", "【5】 表示開始日時が未来", "「表示開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 表示終了日時が過去", "「表示終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("未受付", "【7】 寄附開始日時が未来", "「寄附開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【8】 寄附終了日時が過去", "「寄附終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【9】 上記以外", "すべての条件をクリアした場合")
            render_table(rows)

        # --- マイナビ ---
        with tabs[6]:
            rows = ""
            rows += create_status_row("未登録", "【1】 ステータス空欄", "ファイルの「ステータス」が空欄の場合")
            rows += create_status_row("受付終了", "【2】 売り切れ・受付終了", "ファイルの「ステータス」が <code>売り切れ</code> または <code>受付終了</code> の場合")
            rows += create_status_row("非表示", "【3】 表示設定が非表示", "ファイルの「表示設定」が <code>非表示</code> の場合")
            rows += create_status_row("在庫0", "【4】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合")
            rows += create_status_row("未受付", "【5】 表示開始日時が未来", "「表示開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 表示終了日時が過去", "「表示終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("未受付", "【7】 寄附開始日時が未来", "「寄附開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【8】 寄附終了日時が過去", "「寄附終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【9】 上記以外", "すべての条件をクリアした場合")
            render_table(rows)

        # --- プレミアム ---
        with tabs[7]:
            rows = ""
            rows += create_status_row("未登録", "【1】 公開ステータス空欄", "ファイルの「公開ステータス」が空欄（または該当SKUなし）の場合")
            rows += create_status_row("非表示", "【2】 非公開/下書き", "ファイルの「公開ステータス」が <code>非公開/下書き</code> の場合")
            rows += create_status_row("在庫0", "【3】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【4】 公開期間設定なし", "「公開開始日時」と「公開終了日時」が共に空欄の場合")
            rows += create_status_row("未受付", "【5】 公開開始日時が未来", "「公開開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 公開終了日時が過去", "「公開終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【7】 上記以外", "ステータスが「公開」で、在庫・期間の条件をクリアした場合")
            render_table(rows)

        # --- JRE ---
        with tabs[8]:
            rows = ""
            rows += create_status_row("未登録", "【1】 返礼品コードなし", "ファイルに該当の「品番1」が存在しない場合")
            rows += create_status_row("非表示", "【2】 掲載NG / 期間外", "ステータスが「掲載不可」、または「掲載期間」が範囲外の場合")
            rows += create_status_row("在庫0", "【3】 在庫数が 0", "在庫種別が「無制限」以外で、かつ「在庫数」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【4】 販売期間設定なし", "「販売期間(開始)」と「販売期間(終了)」が共に空欄の場合")
            rows += create_status_row("未受付", "【5】 販売期間(開始)が未来", "「販売期間(開始)」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 販売期間(終了)が過去", "「販売期間(終了)」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【7】 上記以外", "すべての条件をクリアした場合")
            render_table(rows)

        # --- さとふる ---
        with tabs[9]:
            rows = ""
            rows += create_status_row("未登録", "【1】 返礼品コードなし", "さとふる/さとふる在庫ファイルに該当のコードが存在しない場合")
            rows += create_status_row("非表示", "【2】 公開フラグが 2", "さとふるファイルの「公開フラグ」が <code>2</code> の場合")
            rows += create_status_row("在庫0", "【3】 全在庫数が 0", "さとふる在庫ファイルの「全在庫数」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【4】 受付期間設定なし", "「受付開始日」と「受付終了日」が共に空欄の場合")
            rows += create_status_row("未受付", "【5】 受付開始日が未来", "さとふる在庫ファイルの「受付開始日」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【6】 受付終了日が過去", "さとふる在庫ファイルの「受付終了日」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【7】 上記以外", "期間内など、上記条件に該当しない場合")
            render_table(rows)

        # --- Amazon ---
        with tabs[10]:
            rows = ""
            rows += create_status_row("未登録", "【1】 SKUなし", "ファイルに該当の「出品者SKU」が存在しない場合")
            rows += create_status_row("在庫0", "【2】 数量が 0", "ファイルの「数量」が <code>0</code> の場合")
            rows += create_status_row("公開中", "【3】 上記以外", "行が存在し、「数量」が1以上の場合")
            render_table(rows)

        # --- 百選 ---
        with tabs[11]:
            rows = ""
            rows += create_status_row("未登録", "【1】 返礼品コードなし", "ファイルに該当の「返礼品コード」が存在しない場合")
            rows += create_status_row("非表示", "【2】 公開フラグが 0", "ファイルの「公開フラグ」が <code>0</code> の場合")
            rows += create_status_row("在庫0", "【3】 在庫数が 0", "ファイルの「在庫数」が <code>0</code> の場合")
            rows += create_status_row("未受付", "【4】 公開開始日時が未来", "「公開開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【5】 公開終了日時が過去", "「公開終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("未受付", "【6】 申込開始日時が未来", "「申込開始日時」が、<strong>本日より後の日付</strong>の場合")
            rows += create_status_row("受付終了", "【7】 申込終了日時が過去", "「申込終了日時」が、<strong>本日より前の日付</strong>の場合")
            rows += create_status_row("公開中", "【8】 上記以外", "すべての条件をクリアした場合")
            render_table(rows)