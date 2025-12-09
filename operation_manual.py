import streamlit as st
import os

# --- ダイアログ（モーダルウィンドウ）の定義 ---
# width="large" に設定
@st.dialog("操作マニュアル", width="large")
def show_instructions(): 
    # --- CSSで画像を強制的に拡大させる ---
    # Pythonのパラメータを使わず、CSSで制御することで
    # 初回表示時のサイズ崩れを防ぎ、警告も回避します。
    st.markdown("""
        <style>
        /* ダイアログ内のst.image画像を強制的に横幅100%にする */
        div[data-testid="stDialog"] div[data-testid="stImage"] img {
            width: 100% !important;
            max-width: 100% !important;
            height: auto !important;
            object-fit: contain !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- スクロールエリアの定義 ---
    # height=600 (ピクセル)
    # border=True で枠線を付ける
    with st.container(height=700, border=True):
        
        # 楽天の必須項目をリスト定義
        rakuten_items = [
            "商品管理番号（商品URL）", "商品番号", "商品名", "倉庫指定", "サーチ表示",
            "販売期間指定（開始日時）", "販売期間指定（終了日時）",
            "注文ボタン", "SKU管理番号", "システム連携用SKU番号", "在庫数", "SKU倉庫指定"
        ]

        # タグ風デザインのHTMLを生成
        # インデントによるコードブロック化を防ぐため、1行で記述
        tags_html = ""
        for item in rakuten_items:
            tags_html += f"""<span style="display: inline-block; padding: 4px 12px; margin: 4px 2px; background-color: #f0f2f6; color: #31333F; border: 1px solid #d1d5db; border-radius: 16px; font-size: 0.85em; font-weight: 500;">{item}</span>"""

        st.markdown(f"""
        本アプリは各ポータルにおける返礼品の掲載状況を一元確認できるツールで、掲載／停止の見落としを防ぐことを目的としています。
        ポータルのデータファイルを読み込むことで、各ポータルの掲載状況を表示します。

        ---

        ## 🗃️1. データベース管理（※必要に応じて）
        以下については、[こちらのスプレッドシート](https://docs.google.com/spreadsheets/d/1Yb-0DLDb-IAKIxDkhaSZxDl-zd2iDHZ3aX3_4mSiQyI)の情報をもとに掲載状況の結果が出力されます。

        * **「定期便フラグ」列**：「定期便DB」シートを参照
        * **「事業者名」列**　　：「事業者DB」シートを参照
        
        必要に応じてスプレッドシートの更新をお願いします。
        > **⚠️ 注意**
        > 
        > 新しいデータは一番下の行に新規追加してください。既存のデータを更新する場合は、他のデータを更新しないように注意してください。
        > 
        > また、登録するデータは重複しないようにお願いします。

        ## 📥2. インポート

        **① フィルター**
        
        フィルターエリア「返礼品コード」または「事業者コード」にフィルター対象のコードを入力をすることで、読み込むデータを絞り込むことができます。データを絞ることでアプリの動作が軽くなります。
        > **⚠️ 注意**
        > 
        > ※「楽天」「チョイス在庫」「さとふる在庫」「百選在庫」は仕様上、このフィルターの対象外です。
 
        **② ファイルのアップロード**
        
        各ポータルからダウンロードしたデータファイルをアップロードしてください。（複数選択可）
        > **⚠️ 注意**
        > 
        > ファイル名に「ポータル名」を含めたファイルをアップロードしてください。在庫ファイルは「ポータル名在庫」を含めてください。
        > 
        > 「チョイス」と「チョイス在庫」、「さとふる」と「さとふる在庫」、「百選」と「百選在庫」は、それぞれ必ずセットでアップロードしてください。

        **「楽天」は下記の項目が必要です。**
                    
        <div style="margin-top: 5px; margin-bottom: 15px;">
        {tags_html}
        </div>
        """, unsafe_allow_html=True)

        # --- 楽天の画像表示エリア ---
        st.markdown(f"""
        **管理画面で下記（キャプチャ）の項目にチェックを入れてダウンロードしてください。**""")
        
        # 絶対パスを動的に生成して読み込みエラーを防ぐ
        base_dir = os.path.dirname(os.path.abspath(__file__))
        img_path1 = os.path.join(base_dir, "static", "楽天1.png")
        img_path2 = os.path.join(base_dir, "static", "楽天2.png")
        img_path3 = os.path.join(base_dir, "static", "楽天3.png")

        # 画像を縦に並べて表示
        # ★ CSSで幅を制御するため、st.image にはサイズ指定パラメータを渡さない
        
        if os.path.exists(img_path1):
            st.image(img_path1)
        else:
            st.error(f"画像が見つかりません: {img_path1}")

        st.write("") 

        if os.path.exists(img_path2):
            st.image(img_path2)
        else:
            st.error(f"画像が見つかりません: {img_path2}")

        st.write("")

        if os.path.exists(img_path3):
            st.image(img_path3)
        else:
            st.error(f"画像が見つかりません: {img_path3}")
        # --------------------------

        st.markdown(f"""
        ## 🚀3. 実行
        基準となる「ポータル」と「基準日」を選択して、「掲載状況を表示」ボタンを押下してください。
        
        上記「2. インポート」が完了すると、「ポータル」の選択、「基準日」の設定、「掲載状況を表示」ボタンが有効化されます。
        
        **① ベースポータル選択**
        
        選択したポータルの返礼品データを基準として、全ポータルの掲載状況を横並びで比較・一覧化します。

        **② 基準日設定**
        
        ステータス判定（公開中、未受付、受付終了など）の基準となる日付です。
        * デフォルトは**本日**です。
        * 日付を変更することで、ステータス遷移のシミュレーション確認が可能です。
        
        """, unsafe_allow_html=True)