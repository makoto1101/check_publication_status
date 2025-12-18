import streamlit as st
from datetime import datetime, timedelta, timezone
from googleapiclient.errors import HttpError

def get_sheet_id(service, spreadsheet_id, sheet_name):
    """シート名からシートID(整数)を取得する。見つからない場合はNoneを返す"""
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in spreadsheet.get('sheets', []):
            if sheet['properties']['title'] == sheet_name:
                return sheet['properties']['sheetId']
        return None
    except Exception as e:
        # 取得時のエラーは致命的でない場合もあるのでコンソールへ
        print(f"Error getting sheet ID: {e}")
        return None

def create_monthly_log_sheet(service, spreadsheet_id, sheet_name):
    """
    月別のログシートを新規作成し、ヘッダーと詳細な書式（列幅など）を設定する関数
    """
    try:
        # 1. シートの追加（同時に1行目を固定）
        add_sheet_request = {
            "addSheet": {
                "properties": {
                    "title": sheet_name,
                    "gridProperties": {
                        # 固定行(1行)以外に最低1行スクロール用が必要なため、2にする
                        "rowCount": 2, 
                        "columnCount": 7, # A-G列
                        "frozenRowCount": 1 # 1行目を固定
                    }
                }
            }
        }
        
        # シートを作成してIDを取得
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [add_sheet_request]}
        ).execute()
        
        new_sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']

        # 2. ヘッダーの書き込み
        headers = [
            "実行日時", 
            "ユーザー名", 
            "インポートファイル名", 
            "基準ポータル", 
            "基準日", 
            "掲載状況表示ポータル名", 
            "エラーメッセージ"
        ]
        
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]}
        ).execute()

        # 3. 書式と列幅の設定
        requests = []

        # A. 行の高さ設定 (1行目を40pxに)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": new_sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1
                },
                "properties": {"pixelSize": 40},
                "fields": "pixelSize"
            }
        })

        # B. 列幅の設定 (指定されたサイズ)
        column_widths = [
            (0, 200), # A: 実行日時
            (1, 300), # B: ユーザー名
            (2, 300), # C: インポートファイル名
            (3, 100), # D: 基準ポータル
            (4, 100), # E: 基準日
            (5, 300), # F: 掲載状況表示ポータル名
            (6, 300)  # G: エラーメッセージ
        ]

        for col_idx, width in column_widths:
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": new_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col_idx,
                        "endIndex": col_idx + 1
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize"
                }
            })

        # C. ヘッダーセルの書式設定 (A1:G1)
        # 背景色 #f3f3f3, 中央揃え, 太字なし
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": new_sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {
                            "red": 0.9529,
                            "green": 0.9529,
                            "blue": 0.9529
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "bold": False # 太字にしない
                        }
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
            }
        })

        # まとめて実行
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
        
        return new_sheet_id

    except Exception as e:
        # エラーを表示
        st.error(f"ログシート作成中にエラーが発生しました: {e}")
        return None

def write_log(service, log_spreadsheet_id, user_name, imported_files, base_portal, base_date, displayed_portals, error_msg=""):
    """
    指定されたログ用スプレッドシートの月別シート(logs_YYYYMM)にログを追記する。
    """
    # 1. 日本時間で現在時刻と年月を取得
    JST = timezone(timedelta(hours=9), 'JST')
    now_jst = datetime.now(JST)
    now_str = now_jst.strftime("%Y/%m/%d %H:%M:%S")
    
    # シート名決定: logs_202512 など
    target_sheet_name = f"logs_{now_jst.strftime('%Y%m')}"
    
    files_str = ", ".join(imported_files) if imported_files else ""
    portals_str = ", ".join(displayed_portals) if displayed_portals else ""
    
    row_data = [
        now_str, user_name, files_str, base_portal, base_date, portals_str, error_msg
    ]

    try:
        # 2. シートIDの確認
        sheet_id = get_sheet_id(service, log_spreadsheet_id, target_sheet_name)
        
        # シートがない場合は作成 (書式設定含む)
        if sheet_id is None:
            sheet_id = create_monthly_log_sheet(service, log_spreadsheet_id, target_sheet_name)
            if sheet_id is None:
                st.error("ログシートの作成に失敗したため、ログ記録を中断します。")
                return 

        # 3. 行の挿入 (2行目に挿入)
        requests = [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 1, # 0始まりのインデックス。1は「2行目」
                        "endIndex": 2
                    },
                    "inheritFromBefore": False # 上の行(ヘッダー)の書式を引き継がない
                }
            }
        ]
        service.spreadsheets().batchUpdate(
            spreadsheetId=log_spreadsheet_id,
            body={"requests": requests}
        ).execute()

        # 4. データの書き込み
        range_name = f"{target_sheet_name}!A2:G2"
        body = { "values": [row_data] }
        
        service.spreadsheets().values().update(
            spreadsheetId=log_spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        # 5. データ行の書式設定 (中央揃えの適用)
        format_requests = []
        
        # A列～B列を中央揃え
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1, # 2行目
                    "endRowIndex": 2,
                    "startColumnIndex": 0, # A列
                    "endColumnIndex": 2    # B列の次まで(A,B)
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })
        
        # D列～E列を中央揃え
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 3, # D列
                    "endColumnIndex": 5    # E列の次まで(D,E)
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        })

        service.spreadsheets().batchUpdate(
            spreadsheetId=log_spreadsheet_id,
            body={"requests": format_requests}
        ).execute()

    except HttpError as err:
        st.error(f"ログ記録中にAPIエラーが発生しました: {err}")
    except Exception as e:
        st.error(f"ログ記録中に予期せぬエラーが発生しました: {e}")