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
    
    # app.py側で code が .upper() されているため、大文字で検索
    row = lookup_maps.get(portal, {}).get(code)
    
    # --- チョイスの場合の親コードフォールバック検索 ---
    # 他ポータルがベースの場合、検索キー(code)はサフィックスなしの通常コードで渡ってくる。
    # チョイス側に通常コード(子)がなく、親コードのみが存在する場合に対応するため、
    # ここで親コード(サフィックスあり)での再検索を行う。
    if portal == 'チョイス' and not row:
        parent_key = str(code).strip() + '（チョイス親）'
        row = lookup_maps.get(portal, {}).get(parent_key)
        # ※この row を使って後続の判定を行うため、判定ロジック自体は子と同じものが適用される
    # ------------------------------------------------

    # 楽天・さとふる・ぐるなび以外は、row（=コードに対応する行データ）がなければ「未登録」
    # ※ぐるなびはロジック内で個別に row チェックを行うため、ここでは対象外とする（または下記ロジックで対応）
    if not row and portal not in ['楽天', 'さとふる', 'ぐるなび']: 
        return '未登録'

    # --- チョイスのステータス判定ロジック ---
    if portal == 'チョイス':
        # (ヘッダー無しのファイルなのでインデックス番号で指定するが、変数名を分かりやすく変更)
        # CT列 (97) -> 表示有無 (0=非表示, 1=表示)
        # ※ row取得時に親コードへフォールバックしている場合でも、get_val内で lookup_maps を再検索するため
        #    ここで使用する code も row に合わせて親キーにする必要があるか？
        #    → get_val は引数の code を使って再検索を行う仕様。
        #      row が親キーで取得された場合、code は子キーのままなので get_val でヒットしない可能性がある。
        #      したがって、row から正しいキー(key_col_str)を取得して上書きするか、
        #      row自体から値を取得するように変更するのが理想だが、get_valはlookup_maps依存。
        #      ここでは簡易的に、もし row が見つかっていて、かつ元の code で get_val が失敗する（空文字）ようなら
        #      親キーで get_val を呼ぶ必要があるが、get_val は汎用関数のため、
        #      ここで code を「実際にヒットしたキー」に差し替えるのが安全。
        
        actual_code = code
        if row:
            # row['key_col_str'] に検索に使ったキーが入っている（app.pyの読み込み時に設定済みと仮定）
            # もし入っていなければ、parent_key を試す
            if 'key_col_str' in row:
                actual_code = row['key_col_str']
            elif str(code).strip() + '（チョイス親）' in lookup_maps.get(portal, {}):
                 # フォールバックしたと推測される場合
                 if not lookup_maps.get(portal, {}).get(code):
                     actual_code = str(code).strip() + '（チョイス親）'

        display_flag = get_val('チョイス', actual_code, 97)
        # CU列 (98) -> 受付開始日時
        start_date = format_date(get_val('チョイス', actual_code, 98))
        # CV列 (99) -> 受付終了日時
        end_date = format_date(get_val('チョイス', actual_code, 99))
        
        # チョイス在庫ファイルから在庫数を取得 (x_val の元データ)
        # (チョイス在庫, 4) -> 在庫数
        # ★在庫ファイル側も親キーで検索する必要がある
        #   app.py側でチョイス在庫の読み込み時に親判定＆サフィックス付与はしていない（と思われる）場合、
        #   在庫ファイルは「元のID」で紐づくため、actual_code が親サフィックス付きだとヒットしない可能性がある。
        #   しかし、app.py の robust_read_file -> チョイス親判定処理 は「チョイス」シートに対して行われている。
        #   「チョイス在庫」には親フラグ列がないため、サフィックスは付いていないはず。
        #   -> なので、在庫取得には「元の code (サフィックスなし)」を使うのが正解に近いが、
        #      親行の場合、ID（1列目）自体は子と同じ値が入っているはずなので、
        #      actual_code がサフィックス付きでも、在庫検索用のマップ(lookup_maps['チョイス在庫'])のキーがどうなっているか次第。
        #      app.py L.635付近で在庫データのキーは `mapped_codes` (返礼品コード) になっている。
        #      親行の返礼品コードはサフィックス付きに置換されている。
        #      在庫データの `mapped_codes` も親行に対してはサフィックス付きになるよう app.py 側で整合性が取れている必要がある。
        #      
        #      提供された app.py を見ると、チョイス在庫の処理（L.620以降）では
        #      `df_choice` から IDマップを作成している。
        #      この `df_choice` は既に親判定処理（L.583）通過後なので、親行の102列目はサフィックス付きになっている。
        #      したがって、`id_map` も `{ID: 'CODE（チョイス親）'}` となっている。
        #      よって、在庫ファイルのキーもサフィックス付きになっている。
        #      結論：在庫取得も `actual_code`（サフィックス付き）で行えばOK。

        stock_lookup = get_val('チョイス在庫', actual_code, 4)
        
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
        rakuten_product_id_map = kwargs.get('rakuten_product_id_map', {})
        rakuten_management_id_map = kwargs.get('rakuten_management_id_map', {})
        # グループマップを取得
        rakuten_group_map = kwargs.get('rakuten_group_map', {})

        # A列(code)は引数で渡ってくるベースポータルの商品番号
        # app.py側で大文字化済みのため、そのまま (大文字)
        product_id = code

        # ■ Z列 (SKU親コード)
        # product_id (大文字) で rakuten_product_id_map (キー大文字) を検索
        product_row = rakuten_product_id_map.get(product_id)
        sku_parent_code_raw = product_row.get("商品管理番号（商品URL）", "なし") if product_row else "なし"
        
        # キーを正規化
        # sku_parent_code は「生」のコード (大文字小文字混在)
        sku_parent_code = str(sku_parent_code_raw).strip() if sku_parent_code_raw and sku_parent_code_raw != "なし" else "なし"

        # 【1】未登録
        if sku_parent_code == "なし":
            return "未登録"

        # ■ AH列 (在庫数) -> AE列
        stock_count_raw = ""
        # product_id (大文字) で検索
        # product_row は上記で取得済み
        
        # 1. まず商品番号で在庫数をチェック (J列)
        if product_row and product_row.get("在庫数", "") != "":  
            stock_count_raw = product_row.get("在庫数")
        
        # 2. 値がない場合、グループ情報を用いたフォールバックチェック
        else:
            # 商品管理番号（URL）をキーにしてグループを取得
            target_group_key = sku_parent_code.upper()
            group_rows = rakuten_group_map.get(target_group_key, [])
            group_len = len(group_rows)

            if group_len == 2:
                # グループが2件の場合、もう一方の行（すぐ下の行など）の在庫を参照する
                for gr in group_rows:
                    # 自分自身（現在のproduct_id）でない行を探す
                    g_code = str(gr.get('商品番号', '')).strip().upper()
                    if g_code != product_id:
                        val = gr.get('在庫数', '')
                        if val != '':
                            stock_count_raw = val
                        break # 値が見つかれば終了（あるいは相方を確認したら終了）
            
            elif group_len >= 3:
                # グループが3件以上の場合、在庫チェックをスキップする
                # (= stock_count_raw は空文字のまま -> 後続の判定で "在庫0" にならない)
                pass
        
        stock_status = "在庫0" if stock_count_raw == "0" or stock_count_raw == "在庫0" else stock_count_raw

        # ■ AA列 (倉庫指定)
        warehouse_status = ""
        
        # 1. まず自分自身（商品行）の倉庫指定を見る
        if product_row and product_row.get("倉庫指定", "") == "1":
            warehouse_status = "1"
        
        # 2. 次に、グループ（在庫行）側の倉庫指定を見る
        else:
            if sku_parent_code != "なし":
                # 商品管理番号（URL）をキーにしてグループを取得
                target_group_key = sku_parent_code.upper()
                group_rows = rakuten_group_map.get(target_group_key, [])
                group_len = len(group_rows)

                if group_len == 2:
                    # グループが2件（ペア）の場合、もう一方の行を確認する
                    for gr in group_rows:
                        # 自分自身（現在のproduct_id）でない行を探す
                        g_code = str(gr.get('商品番号', '')).strip().upper()
                        if g_code != product_id:
                            # 在庫行の「倉庫指定」または「SKU倉庫指定」が1なら倉庫扱いとする
                            if gr.get("倉庫指定", "") == "1" or gr.get("SKU倉庫指定", "") == "1":
                                warehouse_status = "1"
                            break
                
                elif group_len >= 3:
                    # グループが3件以上の場合、判定をスキップする（イレギュラーケース）
                    # 必要に応じて全行チェックなどに拡張可能
                    pass

        # ■ AB列 (サーチ表示)
        search_display = ""
        
        # 親情報の管理行を取得
        management_row = None
        if sku_parent_code and sku_parent_code != "なし":
             management_row = rakuten_management_id_map.get(sku_parent_code.upper())

        if not sku_parent_code or sku_parent_code == "なし":
            # product_row は上記で取得済み (product_id大文字)
            if product_row: 
                search_display = product_row.get("サーチ表示", "") # E列
        else:
            # sku_parent_code (生) を .upper() して検索
            if management_row: 
                search_display = management_row.get("サーチ表示", "") # E列

        # ■ AF/AG列 -> AC/AD列 (販売期間)
        start_date_raw = ""
        # product_row は上記で取得済み (product_id大文字)
        if product_row and product_row.get("販売期間指定（開始日時）", "") != "": # F列
            start_date_raw = product_row.get("販売期間指定（開始日時）")
        else:
            if management_row: 
                start_date_raw = management_row.get("販売期間指定（開始日時）", "")

        end_date_raw = ""
        # product_row は上記で取得済み (product_id大文字)
        if product_row and product_row.get("販売期間指定（終了日時）", "") != "": # G列
            end_date_raw = product_row.get("販売期間指定（終了日時）")
        else:
            if management_row: 
                end_date_raw = management_row.get("販売期間指定（終了日時）", "")
            
        start_date_formatted = format_date(start_date_raw)
        end_date_formatted = format_date(end_date_raw)

        # --- ■ Y列 (最終ステータス判定) ---
        
        # 【2】倉庫
        if warehouse_status == "1":
            return "倉庫"

        # 【3】在庫0
        if stock_status == "在庫0":
            return "在庫0"

        # 【4】非表示 (サーチ表示が0)
        # スプレッドシートの VALUE(AB4:AB)=0 に相当するロジック
        is_hidden = False
        if search_display != "": 
            try:
                # 文字列を数値(float)に変換
                if float(search_display) == 0:
                    is_hidden = True # "0" や "0.0" の場合は「非表示」
            except ValueError:
                pass
        
        if is_hidden:
            return "非表示"

        # 【5】注文ボタン (0なら未受付)
        # (処理順序: サーチ表示の後、日付判定の前)
        order_button_val = ""
        if product_row and product_row.get("注文ボタン", "") != "":
            order_button_val = product_row.get("注文ボタン")
        else:
            if management_row:
                order_button_val = management_row.get("注文ボタン", "")

        if order_button_val != "":
            try:
                if float(order_button_val) == 0:
                    return "注文不可"
            except ValueError:
                pass

        # --- 日付判定 ---

        # 【6】販売期間設定なし：公開中
        if not start_date_formatted and not end_date_formatted:
            return "公開中"

        # 【7】販売開始日時が未来：未受付
        if start_date_formatted and start_date_formatted > select_date_str:
            return "未受付"

        # 【8】販売終了日時なし：公開中
        # （開始済みで、かつ終了日がない場合）
        if not end_date_formatted:
            return "公開中"

        # 【9】販売終了日時が過去：受付終了
        if end_date_formatted < select_date_str:
            return "受付終了"

        # 【10】上記以外：公開中
        return "公開中"

    # --- さとふるのステータス判定ロジック ---
    if portal == 'さとふる':
        # --- データの準備 ---
        # 1. メインファイル（さとふる）から「公開フラグ」「お礼品ID」を取得
        pub_flag = row.get('公開フラグ', '') if row else ''
        sato_id = row.get('お礼品ID', '') if row else ''

        # 2. 在庫ファイル（さとふる在庫）の行データをIDで検索
        stock_row = lookup_maps.get('さとふる在庫', {}).get(sato_id) if sato_id else None

        # 3. 在庫ファイルから「在庫数」「日付」を取得
        # （※stock_rowが取得できた場合のみ値を取り出す）
        stock_count = str(stock_row.get('全在庫数', '')) if stock_row else ''
        start_date = format_date(stock_row.get('受付開始日')) if stock_row else ''
        end_date = format_date(stock_row.get('受付終了日')) if stock_row else ''

        # 【1】返礼品コードが存在しない
        if not row or not stock_row: return '未登録'

        # 【2】公開フラグが 2
        if pub_flag == '2': return '非表示'

        # 【3】全在庫数が 0
        if stock_count == '0': return '在庫0'

        # 【4】受付期間設定なし（開始・終了ともに空欄）：公開中
        # （他ポータルと挙動を合わせるため追加）
        if not start_date and not end_date:
            return '公開中'

        # 【5】受付開始日が未来：未受付
        # （★順序変更：終了日判定より先にチェックする）
        if start_date and start_date > select_date_str:
            return '未受付'

        # 【6】受付終了日が過去：受付終了
        if end_date and end_date < select_date_str:
            return '受付終了'

        # 【7】上記以外：公開中
        # （終了日が未来の場合などはここで公開中になる）
        return '公開中'

    # --- JREのステータス判定ロジック ---
    if portal == 'JRE':
        # 掲載（表示）関連
        pub_status = get_val('JRE', code, '掲載ステータス')
        pub_start = format_date(get_val('JRE', code, '掲載期間（開始）'))
        pub_end = format_date(get_val('JRE', code, '掲載期間（終了）'))
        
        # 在庫関連
        stock_type = get_val('JRE', code, '在庫扱いの種別')
        stock_count = get_val('JRE', code, '在庫数')
        
        # 販売（寄附）関連
        sales_start = format_date(get_val('JRE', code, '販売期間（開始）'))
        sales_end = format_date(get_val('JRE', code, '販売期間（終了）'))

        # 【1】未登録
        if not row:
            return '未登録'

        # 【2】非表示（掲載ステータスNG または 掲載期間外）
        is_pub_ng = (pub_status == "掲載不可")
        is_pub_future = (pub_start and pub_start > select_date_str)
        is_pub_past = (pub_end and pub_end < select_date_str)

        if is_pub_ng or is_pub_future or is_pub_past:
            return '非表示'

        # 【3】在庫0
        if stock_type != "無制限" and str(stock_count) == '0':
            return '在庫0'

        # 【4】販売期間設定なし（開始・終了ともに空欄）：公開中
        if not sales_start and not sales_end:
            return '公開中'

        # 【5】販売期間(開始)が未来：未受付
        if sales_start and sales_start > select_date_str:
            return '未受付'

        # 【6】販売期間(終了)が過去：受付終了
        if sales_end and sales_end < select_date_str:
            return '受付終了'

        # 【7】上記以外：公開中
        return '公開中'

    if portal == 'ANA':
        status_flag = get_val('ANA', code, '状態(掲載フラグ)')
        stock_raw = get_val('ANA', code, '在庫数')
        
        stock_status = "在庫0" if stock_raw == '0' else stock_raw
        
        # 掲載期間
        pub_start = format_date(get_val('ANA', code, '掲載開始日'))
        pub_end = format_date(get_val('ANA', code, '掲載終了日'))
        
        # 販売期間
        sale_start = format_date(get_val('ANA', code, '販売開始日'))
        sale_end = format_date(get_val('ANA', code, '販売終了日'))
        
        # 【1】未登録
        if status_flag == '': return '未登録'

        # 【2】非表示
        # 1(非公開) または 9(終息) の場合
        if status_flag == '1' or status_flag == '9': return '非表示'

        # 【3】在庫0
        if stock_status == '在庫0': return '在庫0'
        
        # 【4】掲載開始日が未来：未受付
        if pub_start and pub_start > select_date_str:
            return '未受付'

        # 【5】掲載終了日が過去：受付終了
        if pub_end and pub_end < select_date_str:
            return '受付終了'

        # 【6】販売開始日が未来：未受付
        if sale_start and sale_start > select_date_str:
            return '未受付'

        # 【7】販売終了日が過去：受付終了
        if sale_end and sale_end < select_date_str:
            return '受付終了'

        # 【8】上記以外：公開中
        return '公開中'

    if portal == 'ふるなび':
        sales_flag = get_val('ふるなび', code, '販売フラグ')
        public_flag = get_val('ふるなび', code, '公開フラグ')
        stock_status = "在庫0" if get_val('ふるなび', code, '在庫数') == '0' else ''
        start_date = format_date(get_val('ふるなび', code, '公開開始日'))
        end_date = format_date(get_val('ふるなび', code, '公開終了日'))
        
        # 【1】未登録
        if sales_flag == '': return '未登録'
        # 【2】非表示
        if sales_flag == 'off' or public_flag == 'off': return '非表示'
        # 【3】在庫0
        if stock_status == '在庫0': return '在庫0'
        
        # 【4】公開期間設定なし（開始・終了ともに空欄）：公開中
        if not start_date and not end_date:
            return '公開中'

        # 【5】公開開始日時が未来：未受付
        if start_date and start_date > select_date_str:
            return '未受付'

        # 【6】公開終了日時が過去：受付終了
        if end_date and end_date < select_date_str:
            return '受付終了'

        # 【7】上記以外：公開中
        return '公開中'

    if portal == 'JAL':
        # 値取得
        status = get_val('JAL', code, 'ステータス')
        display_setting = get_val('JAL', code, '表示設定')

        stock_count = get_val('JAL', code, '在庫数')
        stock_setting = get_val('JAL', code, '在庫設定')
        stock_status = ""
        if stock_count == "":
            if stock_setting == "在庫設定なし":
                stock_status = "無制限"
            else:
                stock_status = stock_setting
        elif str(stock_count) == '0':
            stock_status = "在庫0"
        else:
            stock_status = stock_count

        disp_start = format_date(get_val('JAL', code, '表示開始日時'))
        disp_end = format_date(get_val('JAL', code, '表示終了日時'))
        kifu_start = format_date(get_val('JAL', code, '寄附開始日時'))
        kifu_end = format_date(get_val('JAL', code, '寄附終了日時'))

        # 【1】ステータスが空欄
        if status == "": return '未登録'
        
        # 【2】ステータスが 品切れ
        if status == "品切れ": return '受付終了'

        # 【3】ステータスが 受付終了
        if status == "受付終了": return '受付終了'
        
        # 【4】表示設定が 非表示
        if display_setting == "非表示": return '非表示'
            
        # 【5】在庫数が0
        if stock_status == "在庫0": return '在庫0'
        
        # 【6】表示開始日時が未来 (未受付)
        if disp_start and disp_start > select_date_str:
            return '未受付'
            
        # 【7】表示終了日時が過去 (受付終了)
        if disp_end and disp_end < select_date_str:
            return '受付終了'
            
        # 【8】寄附開始日時が未来 (未受付)
        if kifu_start and kifu_start > select_date_str:
            return '未受付'
            
        # 【9】寄附終了日時が過去 (受付終了)
        if kifu_end and kifu_end < select_date_str:
            return '受付終了'
            
        # 【10】いずれにも該当しない -> 公開中
        return '公開中'
            
    if portal == 'まいふる':
        status = get_val('まいふる', code, 'ステータス')
        display_setting = get_val('まいふる', code, '状態')
        stock_count_raw = get_val('まいふる', code, '在庫数')
        
        display_start_date = format_date(get_val('まいふる', code, '表示開始日時'))
        display_end_date = format_date(get_val('まいふる', code, '表示終了日時'))
        kifu_start_date = format_date(get_val('まいふる', code, '寄附開始日時'))
        kifu_end_date = format_date(get_val('まいふる', code, '寄附終了日時'))

        # 【1】ステータスが空欄
        if status == "": return '未登録'

        # 【2】ステータスが 売り切れ
        if status == "売り切れ": return '受付終了'

        # 【3】ステータスが 受付終了
        if status == "受付終了": return '受付終了'

        # 【4】状態が 非表示
        if display_setting == "非表示": return '非表示'

        # 【5】在庫数が 0
        if stock_count_raw == '0': return '在庫0'
        
        # 【6】表示開始日時が未来
        if display_start_date and display_start_date > select_date_str:
            return '未受付'
        
        # 【7】表示終了日時が過去
        if display_end_date and display_end_date < select_date_str:
            return '受付終了'
        
        # 【8】寄附開始日時が未来
        if kifu_start_date and kifu_start_date > select_date_str:
            return '未受付'
            
        # 【9】寄附終了日時が過去
        if kifu_end_date and kifu_end_date < select_date_str:
            return '受付終了'
        
        # 【10】いずれにも該当しない -> 公開中
        return '公開中'

    if portal == 'マイナビ':
        status = get_val('マイナビ', code, 'ステータス')
        display_setting = get_val('マイナビ', code, '表示設定')
        stock_count_raw = get_val('マイナビ', code, '在庫数')
        
        display_start_date = format_date(get_val('マイナビ', code, '表示開始日時'))
        display_end_date = format_date(get_val('マイナビ', code, '表示終了日時'))
        kifu_start_date = format_date(get_val('マイナビ', code, '寄附開始日時'))
        kifu_end_date = format_date(get_val('マイナビ', code, '寄附終了日時'))
        
        # 【1】ステータスが空欄
        if status == "": return '未登録'

        # 【2】ステータスが 売り切れ
        if status == "売り切れ": return '受付終了'

        # 【3】ステータスが 受付終了
        if status == "受付終了": return '受付終了'

        # 【4】表示設定が 非表示
        if display_setting == "非表示": return '非表示'

        # 【5】在庫数が 0
        if stock_count_raw == '0': return '在庫0'

        # 【6】表示開始日時が未来
        if display_start_date and display_start_date > select_date_str:
            return '未受付'

        # 【7】表示終了日時が過去
        if display_end_date and display_end_date < select_date_str:
            return '受付終了'
        
        # 【8】寄附開始日時が未来
        if kifu_start_date and kifu_start_date > select_date_str:
            return '未受付'
            
        # 【9】寄附終了日時が過去
        if kifu_end_date and kifu_end_date < select_date_str:
            return '受付終了'

        # 【10】いずれにも該当しない -> 公開中
        return '公開中'
            
    if portal == 'プレミアム':
        public_status = get_val('プレミアム', code, '公開ステータス')
        stock_count_raw = get_val('プレミアム', code, '在庫数')
        start_date = format_date(get_val('プレミアム', code, '公開開始日時'))
        end_date = format_date(get_val('プレミアム', code, '公開終了日時'))

        # 【1】未登録
        if not row or public_status == "":
            return '未登録'
        
        # 【2】非表示
        if public_status == "非公開/下書き":
            return '非表示'

        # 【3】在庫0
        if stock_count_raw == '0':
            return '在庫0'

        # 【4】期間設定なし（開始・終了ともに空欄）：公開中
        if not start_date and not end_date:
            return '公開中'

        # 【5】公開開始日が未来：未受付
        if start_date and start_date > select_date_str:
            return '未受付'

        # 【6】公開終了日が過去：受付終了
        if end_date and end_date < select_date_str:
            return '受付終了'

        # 【7】上記以外：公開中
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
    
    # --- 百選のステータス判定ロジック ---
    if portal == '百選':
        # 【1】返礼品コードなし：未登録
        # (上位の汎用チェックで row がない場合は '未登録' になっているが、明示的なチェックが必要ならここで)
        if not row: return '未登録'

        # --- データの準備 ---
        public_flag = get_val('百選', code, '公開フラグ')
        pub_start = format_date(get_val('百選', code, '公開開始日時'))
        pub_end = format_date(get_val('百選', code, '公開終了日時'))
        apply_start = format_date(get_val('百選', code, '申込開始日時'))
        apply_end = format_date(get_val('百選', code, '申込終了日時'))

        # 在庫ファイル（百選在庫）のデータを取得
        stock_count = get_val('百選在庫', code, '在庫数')

        # 【2】公開フラグが 0：非表示
        if public_flag == '0': return '非表示'

        # 【3】在庫数が 0：在庫0
        if stock_count == '0': return '在庫0'

        # 【4】公開開始日時が未来：未受付
        if pub_start and pub_start > select_date_str:
            return '未受付'

        # 【5】公開終了日時が過去：受付終了
        if pub_end and pub_end < select_date_str:
            return '受付終了'

        # 【6】申込開始日時が未来：未受付
        if apply_start and apply_start > select_date_str:
            return '未受付'

        # 【7】申込終了日時が過去：受付終了
        if apply_end and apply_end < select_date_str:
            return '受付終了'

        # 上記以外：公開中
        return '公開中'

    # --- ぐるなびのステータス判定ロジック ---
    if portal == 'ぐるなび':
        # 【1】返礼品コードなし：未登録
        # (上位の汎用チェックで row がない場合は '未登録' になっているが、明示的なチェックが必要ならここで)
        if not row: return '未登録'

        # --- データの準備 ---
        public_setting = get_val('ぐるなび', code, '公開設定')
        stock_setting = get_val('ぐるなび', code, '在庫設定')
        stock_count = get_val('ぐるなび', code, '在庫数')

        pub_start = format_date(get_val('ぐるなび', code, '公開開始指定日時'))
        pub_end = format_date(get_val('ぐるなび', code, '公開終了指定日時'))
        sales_start = format_date(get_val('ぐるなび', code, '販売期間指定(開始日時)'))
        sales_end = format_date(get_val('ぐるなび', code, '販売期間指定(終了日時)'))

        # 【2】表示設定が "非表示"：非表示 ("公開設定"が0の場合)
        if str(public_setting) == '0': return '非表示'

        # 【3】在庫数が 0：在庫0 ("在庫設定"が0ではなく、「在庫数」が0の場合)
        if str(stock_setting) != '0' and str(stock_count) == '0': return '在庫0'

        # 【4】公開開始指定日時が未来：未受付
        if pub_start and pub_start > select_date_str:
            return '未受付'

        # 【5】公開終了指定日時が過去：受付終了
        if pub_end and pub_end < select_date_str:
            return '受付終了'

        # 【6】販売期間指定(開始日時)が未来：未受付
        if sales_start and sales_start > select_date_str:
            return '未受付'

        # 【7】販売期間指定(終了日時)が過去：受付終了
        if sales_end and sales_end < select_date_str:
            return '受付終了'

        # 上記以外：公開中
        return '公開中'
    
    # --- あとギフのステータス判定ロジック ---
    if portal == 'あとギフ':
        if not row: return '未登録'

        # データ（列）で判断: 「販売フラグ」列があればふるなび形式
        is_furunavi_type = '販売フラグ' in row

        # --- パターンB: ふるなび形式 ---
        if is_furunavi_type:
            sales_flag = get_val('あとギフ', code, '販売フラグ')
            public_flag = get_val('あとギフ', code, '公開フラグ')
            stock_count_raw = get_val('あとギフ', code, '在庫数')
            
            start_date = format_date(get_val('あとギフ', code, '受付開始日時'))
            end_date = format_date(get_val('あとギフ', code, '受付終了日時'))

            # 【2】 販売フラグ または 公開フラグ が "off" ⇒ 非表示
            if sales_flag == 'off' or public_flag == 'off':
                return '非表示'

            # 【3】 在庫数が 0 ⇒ 在庫0
            if stock_count_raw == '0':
                return '在庫0'

            # 【4】 受付期間設定なし ⇒ 公開中
            if not start_date and not end_date:
                return '公開中'

            # 【5】 受付開始日時が未来 ⇒ 未受付
            if start_date and start_date > select_date_str:
                return '未受付'

            # 【6】 受付終了日時が過去 ⇒ 受付終了
            if end_date and end_date < select_date_str:
                return '受付終了'

            # 【7】 上記以外 ⇒ 公開中
            return '公開中'

        # --- パターンA: チョイス形式 ---
        else:
            target_col = '表示有無 (表示させる場合は半角数字の1、非表示にする場合は半角数字の0)'
            public_setting = get_val('あとギフ', code, target_col)
            
            s_val = str(public_setting).strip()
            
            if s_val == '0' or s_val == '0.0':
                return '非表示'
            elif s_val == '1' or s_val == '1.0':
                return '公開中'
                
            return '公開中'

    return '未実装'