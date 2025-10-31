import re
from datetime import datetime

# --- 日付設定 ---
# このファイルで日付を定義し、app.pyでもこれを使用する
TODAY_STR = datetime.now().strftime('%Y%m%d')

def calculate_status(portal, code, lookup_maps, parent_lookup_maps, **kwargs):
    """ポータルごとの掲載ステータスを計算する"""
    
    def get_val(p, c, col_key, is_parent_lookup=False):
        """
        検索マップから指定したキー（列インデックス or ヘッダー名）の値を取得する
        col_key: チョイス系は int (0, 1, 97...)、その他は str ('在庫数', 'ステータス'...)
        """
        lookup = parent_lookup_maps.get(p) if is_parent_lookup else lookup_maps.get(p)
        row = lookup.get(c) if lookup else None
        
        # rowが存在しないか、row辞書にcol_keyが存在しない場合は空文字を返す
        if row is None:
            return ''
        
        # .get() を使うことで、キーが存在しなくてもエラーにならず、デフォルト値('')を返す
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
                return '受付終了' if end_date < TODAY_STR else '公開中'
        else:
            if start_date > TODAY_STR:
                return '未受付'
            else:
                if not end_date:
                    return '公開中'
                else:
                    return '受付終了' if end_date < TODAY_STR else '公開中'
    
    # --- 楽天のステータス判定ロジック ---
    if portal == '楽天':
        # 外部から渡された辞書を取得
        memo_map = kwargs.get('memo_map', {})
        rakuten_product_id_map = kwargs.get('rakuten_product_id_map', {})
        rakuten_management_id_map = kwargs.get('rakuten_management_id_map', {})
        rakuten_sku_code_map = kwargs.get('rakuten_sku_code_map', {})

        # A列(code)は引数で渡ってくるベースポータルの商品番号
        product_id = code

        # ■ Z列 (SKU親コード)
        sku_parent_code = memo_map.get(product_id)
        if not sku_parent_code:
            product_row = rakuten_product_id_map.get(product_id)
            # 旧: product_row.get(0, "なし") -> 新: ヘッダー名で取得
            sku_parent_code = product_row.get("商品管理番号（商品URL）", "なし") if product_row else "なし"

        if sku_parent_code == "なし":
            return "未登録"

        # ■ AH列 (在庫数) -> AE列
        stock_count_raw = ""
        product_row = rakuten_product_id_map.get(product_id)
        
        # (ヘッダー名で参照)
        if product_row and product_row.get("在庫数", "") != "":  # J列
            stock_count_raw = product_row.get("在庫数")
        else:
            sku_row = rakuten_sku_code_map.get(sku_parent_code)
            if sku_row:
                stock_val = sku_row.get("在庫数", "") # J列
                stock_count_raw = "在庫0" if stock_val == "0" else stock_val
        
        stock_status = "在庫0" if stock_count_raw == "0" or stock_count_raw == "在庫0" else stock_count_raw

        # ■ AA列 (倉庫指定)
        warehouse_status = ""
        sku_row_for_warehouse = rakuten_sku_code_map.get(sku_parent_code)
        product_row_for_warehouse = rakuten_product_id_map.get(product_id)
        # (ヘッダー名で参照)
        if (sku_row_for_warehouse and sku_row_for_warehouse.get("倉庫指定", "") == "1") or \
           (product_row_for_warehouse and product_row_for_warehouse.get("倉庫指定", "") == "1"): # D列
            warehouse_status = "1"

        # ■ AB列 (サーチ表示)
        search_display = ""
        if not sku_parent_code or sku_parent_code == "なし":
            if product_row: 
                search_display = product_row.get("サーチ表示", "") # E列
        else:
            management_row = rakuten_management_id_map.get(sku_parent_code)
            if management_row: 
                search_display = management_row.get("サーチ表示", "") # E列

        # ■ AF/AG列 -> AC/AD列 (販売期間)
        start_date_raw = ""
        if product_row and product_row.get("販売期間指定（開始日時）", "") != "": # F列
            start_date_raw = product_row.get("販売期間指定（開始日時）")
        else:
            management_row = rakuten_management_id_map.get(sku_parent_code)
            if management_row: 
                start_date_raw = management_row.get("販売期間指定（開始日時）", "")

        end_date_raw = ""
        if product_row and product_row.get("販売期間指定（終了日時）", "") != "": # G列
            end_date_raw = product_row.get("販売期間指定（終了日時）")
        else:
            management_row = rakuten_management_id_map.get(sku_parent_code)
            if management_row: 
                end_date_raw = management_row.get("販売期間指定（終了日時）", "")
            
        start_date_formatted = format_date(start_date_raw)
        end_date_formatted = format_date(end_date_raw)

        # ■ Y列 (最終ステータス判定)
        if warehouse_status == "1":
            return "倉庫"
        if stock_status == "在庫0":
            return "在庫0"

        is_hidden = (search_display == "0")

        if not start_date_formatted:
            if not end_date_formatted:
                return "非表示" if is_hidden else "公開中"
            else:
                return "受付終了" if end_date_formatted < TODAY_STR else ("非表示" if is_hidden else "公開中")
        else:
            if start_date_formatted > TODAY_STR:
                return "未受付"
            else:
                if not end_date_formatted:
                    return "非表示" if is_hidden else "公開中"
                else:
                    return "受付終了" if end_date_formatted < TODAY_STR else ("非表示" if is_hidden else "公開中")

    # --- さとふるのステータス判定ロジック ---
    if portal == 'さとふる':
        # (ヘッダー名で参照)
        # 旧: row.get(18, '')
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
            if start_date and start_date > TODAY_STR:
                return '未受付'
            elif end_date < TODAY_STR:
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

        if start_date and start_date > TODAY_STR:
            return '未受付'
        
        if end_date == "":
            return '公開中'
        
        if end_date and end_date < TODAY_STR:
            return '受付終了'
        
        return '公開中'

    if portal == 'ANA':
        # (ヘッダー名で参照)
        status_flag = get_val('ANA', code, '状態(掲載フラグ)')
        stock_raw = get_val('ANA', code, '在庫数')
        
        stock_status = "在庫0" if stock_raw == '0' else stock_raw
        
        start_date = format_date(get_val('ANA', code, '販売開始日'))
        end_date = format_date(get_val('ANA', code, '販売終了日'))
        
        if status_flag == '': return '未登録'
        if status_flag == '1': return '非表示'
        if stock_status == '在庫0': return '在庫0'
        
        if not start_date: 
            return '受付終了' if end_date and end_date < TODAY_STR else '公開中'
        else:
            if start_date > TODAY_STR: return '未受付'
            return '受付終了' if end_date and end_date < TODAY_STR else '公開中'

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
            return '受付終了' if end_date and end_date < TODAY_STR else '公開中'
        else:
            if start_date > TODAY_STR: return '未受付'
            return '受付終了' if end_date and end_date < TODAY_STR else '公開中'

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
        # (旧ロジックは 39, 40, 41, 42 を参照していた)
        # (ヘッダーリスト 39:表示開始, 40:表示終了, 41:寄附開始, 42:寄附終了)
        
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
            return '受付終了' if final_end_date < TODAY_STR else '公開中'
        else:
            if final_start_date > TODAY_STR:
                return '未受付'
            else:
                if not final_end_date:
                    return '公開中'
                return '受付終了' if final_end_date < TODAY_STR else '公開中'
            
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
        if display_start_date and display_start_date > TODAY_STR:
            return '未受付'
        
        if display_end_date == "":
            return '公開中' 
        
        if display_end_date < TODAY_STR:
            return '受付終了'
        
        if kifu_start_date and kifu_start_date > TODAY_STR:
            return '未受付'
            
        if kifu_end_date == "":
            return '公開中' 
        
        if kifu_end_date < TODAY_STR:
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
        if display_start_date and display_start_date > TODAY_STR:
            return '未受付'

        if display_end_date == "":
            return '公開中'

        if display_end_date < TODAY_STR:
            return '受付終了'
        
        if kifu_start_date and kifu_start_date > TODAY_STR:
            return '未受付'
            
        if kifu_end_date == "":
            return '公開中'

        if kifu_end_date < TODAY_STR:
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

        if start_date and start_date > TODAY_STR:
            return '未受付'

        if end_date < TODAY_STR:
            return '受付終了'
        
        return '公開中'

    if portal == 'Amazon':
        if not row: return '未登録'
        stock_count = get_val('Amazon', code, '数量')
        stock_status = "在庫0" if stock_count == '0' else ''
        
        if stock_status == "在庫0": return '在庫0'
        return '公開中'

    return '未実装'