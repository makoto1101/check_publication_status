import re
from datetime import datetime

# --- 日付設定 ---
# 基準日は app.py から引数で渡される

def calculate_status(portal, code, lookup_maps, parent_lookup_maps, select_date_str, **kwargs):
    """ポータルごとの掲載ステータスを計算する"""
    
    def get_val(p, c, col_key, is_parent_lookup=False):
        """
        検索マップから指定したキー（列インデックス or ヘッダー名）の値を取得する (大文字・小文字を区別しない)
        col_key: チョイス系は int (0, 1, 97...)、その他は str ('在庫数', 'ステータス'...)
        """
        if not c: # 検索キー(c)が空なら空文字を返す
            return ''
            
        lookup = parent_lookup_maps.get(p) if is_parent_lookup else lookup_maps.get(p)
        if not lookup:
            return ''

        # 1. 渡されたキー(c)でそのまま検索
        row = lookup.get(c)
        
        # 2. 見つからない場合、c を str に変換して検索
        if row is None and isinstance(c, (int, float)):
            row = lookup.get(str(c))
            
        # 3. それでも見つからない場合、大文字・小文字バリエーションで検索 (str型のみ)
        if row is None and isinstance(c, str):
            c_upper = c.upper()
            if c != c_upper: # cが小文字または混在の場合
                row = lookup.get(c_upper) # 大文字で検索
                
            if row is None:
                c_lower = c.lower()
                if c != c_lower: # cが大文字または混在の場合
                    row = lookup.get(c_lower) # 小文字で検索

        # 最終的にrowが見つからなければ空文字を返す
        if row is None:
            return ''
            
        # rowが見つかった場合、col_keyの値を取得
        return row.get(col_key, '')

    def format_date(date_str):
        """日付文字列を'YYYYMMDD'形式に整形する"""
        if not date_str: return ''
        # ハイフンも除去するため、正規表現を [^0-9] に修正
        return re.sub(r'[^0-9]', '', str(date_str))[:8]

    # app.pyから渡される row 辞書のキーが、ポータルによって
    # int (チョイス系) か str (その他) かが異なる
    
    # チョイス系以外（ヘッダーあり）の場合、rowは { 'ヘッダー名1': '値1', ... }
    # チョイス系（ヘッダーなし）の場合、rowは { 0: '値0', 1: '値1', ... }
    
    # ★ 変更: app.py側で code が .upper() されているため、大文字で検索
    row = lookup_maps.get(portal, {}).get(code)
    
    # 楽天・さとふる以外は、row（=コードに対応する行データ）がなければ「未登録」
    if not row and portal not in ['楽天', 'さとふる']: 
        return '未登録'

    # --- チョイスのステータス判定ロジック ---
    if portal == 'チョイス':
        # (ヘッダー無しのファイルなのでインデックス番号で指定するが、変数名を分かりやすく変更)
        # CT列 (97) -> 表示有無 (0=非表示, 1=表示)
        display_flag = get_val('チョイス', code, 97)
        # CU列 (98) -> 受付開始日時
        start_date = format_date(get_val('チョイス', code, 98))
        # CV列 (99) -> 受付終了日時
        end_date = format_date(get_val('チョイス', code, 99))
        
        # チョイス在庫ファイルから在庫数を取得 (x_val の元データ)
        # (チョイス在庫, 4) -> 在庫数
        stock_lookup = get_val('チョイス在庫', code, 4)
        
        stock_status = "" # (x_val)
        if stock_lookup != "":
            try:
                if float(stock_lookup) == 0:
                    stock_status = "在庫0"
                else:
                    stock_status = stock_lookup # 在庫あり (数値)
            except (ValueError, TypeError):
                stock_status = stock_lookup # "無制限" など

        if display_flag == '':
            return '未登録'
        
        try:
            # 掲載フラグが 0 (または 0.0) なら「非表示」
            if float(display_flag) == 0:
                return '非表示'
        except (ValueError, TypeError):
            pass # "1" や "公開" などの場合は通過

        if stock_status == '在庫0':
            return '在庫0'

        if not start_date:
            if not end_date:
                return '公開中'
            else:
                return '受付終了' if end_date < select_date_str else '公開中'
        else:
            if start_date > select_date_str:
                return '未受付'
            else:
                if not end_date:
                    return '公開中'
                else:
                    return '受付終了' if end_date < select_date_str else '公開中'
    
    # --- 楽天のステータス判定ロジック ---
    if portal == '楽天':
        # 外部から渡された辞書を取得
        memo_map = kwargs.get('memo_map', {})
        rakuten_product_id_map = kwargs.get('rakuten_product_id_map', {})
        rakuten_management_id_map = kwargs.get('rakuten_management_id_map', {})
        rakuten_sku_code_map = kwargs.get('rakuten_sku_code_map', {})

        # A列(code)は引数で渡ってくるベースポータルの商品番号
        # ★ 変更: app.py側で大文字化済みのため、そのまま (大文字)
        product_id = code

        # ■ Z列 (SKU親コード)
        # ★ 変更: product_id (大文字) で memo_map (キー大文字) を検索
        sku_parent_code_raw = memo_map.get(product_id) # memo_map (GSheet) から取得
        
        if not sku_parent_code_raw:
            # ★ 変更: product_id (大文字) で rakuten_product_id_map (キー大文字) を検索
            product_row = rakuten_product_id_map.get(product_id)
            # 旧: product_row.get(0, "なし") -> 新: ヘッダー名で取得
            # ★ 修正: .upper() を削除
            sku_parent_code_raw = product_row.get("商品管理番号（商品URL）", "なし") if product_row else "なし"
        
        # ★ 修正: GSheet/フォールバック両方のキーを正規化
        # ★ 重要: sku_parent_code は「生」のコード (大文字小文字混在)
        sku_parent_code = str(sku_parent_code_raw).strip() if sku_parent_code_raw and sku_parent_code_raw != "なし" else "なし"


        if sku_parent_code == "なし":
            return "未登録"

        # ■ AH列 (在庫数) -> AE列
        stock_count_raw = ""
        # ★ 変更: product_id (大文字) で検索
        product_row = rakuten_product_id_map.get(product_id)
        
        # (ヘッダー名で参照)
        if product_row and product_row.get("在庫数", "") != "":  # J列
            stock_count_raw = product_row.get("在庫数")
        else:
            # ★ 変更: ユーザー要望(A列)に基づき、product_id (A列のコード) で SKU管理番号(H列) を検索
            
            # 1. product_id (大文字のコード、例: "AZA032") で厳密検索
            sku_row = rakuten_sku_code_map.get(product_id)
            
            # 2. 見つからない場合、product_id を小文字 (例: "aza032") にして再検索
            if not sku_row:
                sku_row = rakuten_sku_code_map.get(product_id.lower())

            if sku_row:
                stock_val = sku_row.get("在庫数", "") # J列
                stock_count_raw = "在庫0" if stock_val == "0" else stock_val
        
        stock_status = "在庫0" if stock_count_raw == "0" or stock_count_raw == "在庫0" else stock_count_raw

        # ■ AA列 (倉庫指定)
        warehouse_status = ""
        
        # ★ 変更: product_id (大文字) で親行を検索
        product_row_for_warehouse = rakuten_product_id_map.get(product_id)

        # ★ 変更: SKU管理番号辞書で product_id (大文字) を検索
        sku_row_found_by_product_id = rakuten_sku_code_map.get(product_id)
        if not sku_row_found_by_product_id:
             # ★ 変更: 見つからなければ product_id (小文字) で再検索
            sku_row_found_by_product_id = rakuten_sku_code_map.get(product_id.lower())

        # ★ 変更: SKU管理番号辞書で sku_parent_code (生) を検索
        sku_row_found_by_sku_parent = rakuten_sku_code_map.get(sku_parent_code)
        
        # ★ 変更: product_id または sku_parent_code が SKU管理番号辞書に存在するか
        relevant_sku_row = sku_row_found_by_product_id or sku_row_found_by_sku_parent
        
        if relevant_sku_row:
            # ★ 変更: SKU行が見つかった場合
            # 1. SKU行自体の「倉庫指定」が "1" か確認
            if relevant_sku_row.get("倉庫指定", "") == "1":
                warehouse_status = "1"
            # 2. SKU行が "1" でない場合、親行の「倉庫指定」が "1" か確認
            elif product_row_for_warehouse and product_row_for_warehouse.get("倉庫指定", "") == "1":
                warehouse_status = "1"
        else:
            # ★ 変更: SKU行が見つからなかった場合 (ade007 のケース)
            # 親行 (product_row_for_warehouse) が '倉庫指定=1' であっても、
            # warehouse_status は "" のまま (「倉庫」として扱わない)
            pass

        # ■ AB列 (サーチ表示)
        search_display = ""
        if not sku_parent_code or sku_parent_code == "なし":
            # ★ 変更: product_row は L.151 で取得済み (product_id大文字)
            if product_row: 
                search_display = product_row.get("サーチ表示", "") # E列
        else:
            # ★ 変更: sku_parent_code (生) を .upper() して検索
            management_row = rakuten_management_id_map.get(sku_parent_code.upper())
            if management_row: 
                search_display = management_row.get("サーチ表示", "") # E列

        # ■ AF/AG列 -> AC/AD列 (販売期間)
        start_date_raw = ""
        # ★ 変更: product_row は L.151 で取得済み (product_id大文字)
        if product_row and product_row.get("販売期間指定（開始日時）", "") != "": # F列
            start_date_raw = product_row.get("販売期間指定（開始日時）")
        else:
            # ★ 変更: sku_parent_code (生) を .upper() して検索
            management_row = rakuten_management_id_map.get(sku_parent_code.upper())
            if management_row: 
                start_date_raw = management_row.get("販売期間指定（開始日時）", "")

        end_date_raw = ""
        # ★ 変更: product_row は L.151 で取得済み (product_id大文字)
        if product_row and product_row.get("販売期間指定（終了日時）", "") != "": # G列
            end_date_raw = product_row.get("販売期間指定（終了日時）")
        else:
            # ★ 変更: sku_parent_code (生) を .upper() して検索
            management_row = rakuten_management_id_map.get(sku_parent_code.upper())
            if management_row: 
                end_date_raw = management_row.get("販売期間指定（終了日時）", "")
            
        start_date_formatted = format_date(start_date_raw)
        end_date_formatted = format_date(end_date_raw)

        # ■ Y列 (最終ステータス判定)
        if warehouse_status == "1":
            return "倉庫"
        if stock_status == "在庫0":
            return "在庫0"

        #is_hidden = (search_display == "0")
        # スプレッドシートの VALUE(AB4:AB)=0 に相当するロジック
        is_hidden = False
        if search_display != "": # 空文字でない場合
            try:
                # 文字列を数値(float)に変換
                if float(search_display) == 0:
                    is_hidden = True # "0" や "0.0" の場合は「非表示」
            except ValueError:
                # "1" や "公開" など、数値の0以外、または数値変換不可の場合は is_hidden = False (公開)
                pass
        # search_display が "" (空文字) の場合は、is_hidden = False (公開) のまま

        if not start_date_formatted:
            if not end_date_formatted:
                return "非表示" if is_hidden else "公開中"
            else:
                return "受付終了" if end_date_formatted < select_date_str else ("非表示" if is_hidden else "公開中")
        else:
            if start_date_formatted > select_date_str:
                return "未受付"
            else:
                if not end_date_formatted:
                    return "非表示" if is_hidden else "公開中"
                else:
                    return "受付終了" if end_date_formatted < select_date_str else ("非表示" if is_hidden else "公開中")

    # --- さとふるのステータス判定ロジック ---
    if portal == 'さとふる':
        publication_flag = row.get('公開フラグ', '') if row else ''
        
        if not publication_flag:
            return '未登録'
        
        if publication_flag == '2':
            return '非表示'

        # 在庫チェックを日付判定より先に行う
        satofuru_product_id = row.get('お礼品ID', '')
        if satofuru_product_id:
            stock_file_row = lookup_maps.get('さとふる在庫', {}).get(satofuru_product_id)
            if stock_file_row:
                stock_count = stock_file_row.get('全在庫数', '')
                if stock_count == '0':
                    return '在庫0'

        # 日付による判定
        start_date = format_date(row.get('受付開始日', ''))
        end_date = format_date(row.get('受付終了日', ''))

        if not end_date:
            return '公開中'
        else:
            if start_date and start_date > select_date_str:
                return '未受付'
            elif end_date < select_date_str:
                return '受付終了'
            else:
                return '公開中'

    # --- JREのステータス判定ロジック ---
    if portal == 'JRE':
        # (ヘッダー名で参照)
        publication_status = get_val('JRE', code, '掲載ステータス')
        if publication_status == "":
            return '未登録'
        if publication_status == "掲載不可":
            return '非表示'

        stock_count = get_val('JRE', code, '在庫数')
        stock_unlimited = get_val('JRE', code, '在庫扱いの種別')
        
        stock_status = ""
        if stock_count != "":
            if stock_unlimited == "無制限":
                stock_status = "無制限"
            elif stock_count == '0':
                stock_status = "在庫0"
        
        if stock_status == "在庫0":
            return '在庫0'

        start_date = format_date(get_val('JRE', code, '販売期間（開始）'))
        end_date = format_date(get_val('JRE', code, '販売期間（終了）'))

        if start_date and start_date > select_date_str:
            return '未受付'
        
        if end_date == "":
            return '公開中'
        
        if end_date and end_date < select_date_str:
            return '受付終了'
        
        return '公開中'

    if portal == 'ANA':
        status_flag = get_val('ANA', code, '状態(掲載フラグ)')
        stock_raw = get_val('ANA', code, '在庫数')
        
        stock_status = "在庫0" if stock_raw == '0' else stock_raw
        
        start_date = format_date(get_val('ANA', code, '販売開始日'))
        end_date = format_date(get_val('ANA', code, '販売終了日'))
        
        if status_flag == '': return '未登録'
        if status_flag == '1': return '非表示'
        if stock_status == '在庫0': return '在庫0'
        
        if not start_date: 
            return '受付終了' if end_date and end_date < select_date_str else '公開中'
        else:
            if start_date > select_date_str: return '未受付'
            return '受付終了' if end_date and end_date < select_date_str else '公開中'

    if portal == 'ふるなび':
        sales_flag = get_val('ふるなび', code, '販売フラグ')
        public_flag = get_val('ふるなび', code, '公開フラグ')
        stock_status = "在庫0" if get_val('ふるなび', code, '在庫数') == '0' else ''
        start_date = format_date(get_val('ふるなび', code, '公開開始日'))
        end_date = format_date(get_val('ふるなび', code, '公開終了日'))
        
        if sales_flag == '': return '未登録' # sales_flag(ao_val)を基準に未登録判定
        if sales_flag == 'off' or public_flag == 'off': return '非表示'
        if stock_status == '在庫0': return '在庫0'
        
        if not start_date: 
            return '受付終了' if end_date and end_date < select_date_str else '公開中'
        else:
            if start_date > select_date_str: return '未受付'
            return '受付終了' if end_date and end_date < select_date_str else '公開中'

    if portal == 'JAL':
        status = get_val('JAL', code, 'ステータス')
        display_setting = get_val('JAL', code, '表示設定')

        # --- 在庫数(stock_status)のロジックを再現 ---
        stock_count = get_val('JAL', code, '在庫数')
        stock_setting = get_val('JAL', code, '在庫設定')
        
        stock_status = "" # (aw_val)
        if stock_count == "":
            if stock_setting == "在庫設定なし":
                stock_status = "無制限"
            else:
                stock_status = stock_setting
        elif str(stock_count) == '0':
            stock_status = "在庫0"
        else:
            stock_status = stock_count

        # --- 日付(final_start_date, final_end_date)のロジックを再現 --- 
        start1 = format_date(get_val('JAL', code, '表示開始日時'))
        end1 = format_date(get_val('JAL', code, '表示終了日時'))
        start2 = format_date(get_val('JAL', code, '寄附開始日時'))
        end2 = format_date(get_val('JAL', code, '寄附終了日時'))
        
        # 寄附期間(start2, end2)が優先される
        final_start_date = start2 if start2 else start1
        final_end_date = end2 if end2 else end1

        # --- 最終ステータスの判定ロジック ---
        if status == "":
            return '未登録'
        
        if status == "受付終了" or status == "品切れ":
            return '受付終了'
        
        if display_setting == "非表示":
            return '非表示'
            
        if stock_status == "在庫0":
            return '在庫0'
        
        if not final_start_date:
            if not final_end_date:
                return '公開中'
            return '受付終了' if final_end_date < select_date_str else '公開中'
        else:
            if final_start_date > select_date_str:
                return '未受付'
            else:
                if not final_end_date:
                    return '公開中'
                return '受付終了' if final_end_date < select_date_str else '公開中'
            
    if portal == 'まいふる':
        status = get_val('まいふる', code, 'ステータス')
        display_setting = get_val('まいふる', code, '状態') # ヘッダーリスト「状態」
        stock_count_raw = get_val('まいふる', code, '在庫数')
        
        display_start_date = format_date(get_val('まいふる', code, '表示開始日時'))
        display_end_date = format_date(get_val('まいふる', code, '表示終了日時'))
        kifu_start_date = format_date(get_val('まいふる', code, '寄附開始日時'))
        kifu_end_date = format_date(get_val('まいふる', code, '寄附終了日時'))

        # スプレッドシートのBI列のネストされたIF文のロジックを忠実に再現
        if status == "":
            return '未登録'
        if status == "売り切れ":
            return '非表示'
        if status == "受付終了":
            return '受付終了'
        if display_setting == "非表示":
            return '非表示'
        if stock_count_raw == '0':
            return '在庫0'
        
        if display_start_date and display_start_date > select_date_str:
            return '未受付'
        
        if display_end_date == "":
            return '公開中' 
        
        if display_end_date < select_date_str:
            return '受付終了'
        
        if kifu_start_date and kifu_start_date > select_date_str:
            return '未受付'
            
        if kifu_end_date == "":
            return '公開中' 
        
        if kifu_end_date < select_date_str:
            return '受付終了'
        
        return '公開中'

    if portal == 'マイナビ':
        status = get_val('マイナビ', code, 'ステータス')
        display_setting = get_val('マイナビ', code, '表示設定')
        stock_count_raw = get_val('マイナビ', code, '在庫数')
        
        display_start_date = format_date(get_val('マイナビ', code, '表示開始日時'))
        display_end_date = format_date(get_val('マイナビ', code, '表示終了日時'))
        kifu_start_date = format_date(get_val('マイナビ', code, '寄附開始日時'))
        kifu_end_date = format_date(get_val('マイナビ', code, '寄附終了日時'))
        
        # スプレッドシートのBQ列のネストされたIF文のロジックを忠実に再現
        if status == "":
            return '未登録'
        if status == "売り切れ":
            return '非表示'
        if status == "受付終了":
            return '受付終了'
        if display_setting == "非表示":
            return '非表示'
        if stock_count_raw == '0':
            return '在庫0'
        if display_start_date and display_start_date > select_date_str:
            return '未受付'

        if display_end_date == "":
            return '公開中'

        if display_end_date < select_date_str:
            return '受付終了'
        
        if kifu_start_date and kifu_start_date > select_date_str:
            return '未受付'
            
        if kifu_end_date == "":
            return '公開中'

        if kifu_end_date < select_date_str:
            return '受付終了'

        return '公開中'
            
    if portal == 'プレミアム':
        public_status = get_val('プレミアム', code, '公開ステータス')
        stock_count_raw = get_val('プレミアム', code, '在庫数')
        start_date = format_date(get_val('プレミアム', code, '公開開始日時'))
        end_date = format_date(get_val('プレミアム', code, '公開終了日時'))

        if not row:
            return '未登録'
        
        if public_status == "":
            return '未登録'

        if public_status == "非公開/下書き":
            return '非表示'

        if stock_count_raw == '0':
            return '在庫0'

        if end_date == "":
            return '公開中'

        if start_date and start_date > select_date_str:
            return '未受付'

        if end_date < select_date_str:
            return '受付終了'
        
        return '公開中'

    if portal == 'Amazon':
        # 1. Data_Amazon に SKU がない (row がない) 場合は「未登録」
        if not row: return '未登録'
        
        # 2. '数量' 列を取得し、'0' なら「在庫0」
        stock_count = get_val('Amazon', code, '数量')
        stock_status = "在庫0" if stock_count == '0' else ''
        
        if stock_status == "在庫0": 
            return '在庫0'
            
        # 3. 上記以外は「公開中」
        return '公開中'

    return '未実装'