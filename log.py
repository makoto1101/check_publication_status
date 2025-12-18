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
        print(f"Error getting sheet ID: {e}")
        return None

def create_logs_sheet(service, spreadsheet_id, sheet_name):
    """
    logsシートを新規作成し、1行目にヘッダーを書き込む関数
    戻り値: 新しく作成されたシートのID
    """
    try:
        # 1. シートの追加
        request_body = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": sheet_name,
                            "gridProperties": {
                                "rowCount": 1000,
                                "columnCount": 10
                            }
                        }
                    }
                }
            ]
        }
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=request_body
        ).execute()
        
        new_sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']

        # 2. ヘッダーの書き込み
        headers = ["実行日時", "ユーザー名", "インポートファイル", "基準ポータル", "基準日", "掲載状況表示ポータル", "エラー"]
        
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]}
        ).execute()
        
        return new_sheet_id

    except Exception as e:
        st.error(f"ログシートの自動作成に失敗しました: {e}")
        return None

def write_log(service, spreadsheet_id, user_name, imported_files, base_portal, base_date, displayed_portals, error_msg=""):
    """
    logsシートの2行目にログを挿入する。シートがない場合は自動作成する。
    """
    target_sheet_name = "logs"
    
    # 1. データの整形 (日本時間 JST で取得)
    # タイムゾーンの定義 (UTC+9時間)
    JST = timezone(timedelta(hours=9), 'JST')
    now_jst = datetime.now(JST)
    now_str = now_jst.strftime("%Y/%m/%d %H:%M:%S")
    
    files_str = ", ".join(imported_files) if imported_files else ""
    portals_str = ", ".join(displayed_portals) if displayed_portals else ""
    
    # 記録するデータの配列 (A列～G列)
    row_data = [
        now_str,            # A: 実行日時 (JST)
        user_name,          # B: ユーザー名
        files_str,          # C: インポートファイル
        base_portal,        # D: 基準ポータル
        base_date,          # E: 基準日
        portals_str,        # F: 掲載状況表示ポータル
        error_msg           # G: エラー
    ]

    try:
        # 2. シートIDの取得
        sheet_id = get_sheet_id(service, spreadsheet_id, target_sheet_name)
        
        # シートが見つからない場合、自動作成を試みる
        if sheet_id is None:
            sheet_id = create_logs_sheet(service, spreadsheet_id, target_sheet_name)
            
            if sheet_id is None:
                # 作成にも失敗した場合はログ記録を諦めて終了（アプリは止めない）
                return

        # 3. APIリクエストの作成
        # ステップA: 2行目に行を1行挿入する (既存の行を下げる)
        requests = [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 1, # 0始まりのインデックス。1は「2行目」を指す
                        "endIndex": 2
                    },
                    "inheritFromBefore": False
                }
            }
        ]

        # 行の挿入を実行
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

        # ステップB: 挿入した2行目にデータを書き込む (A2:G2)
        range_name = f"{target_sheet_name}!A2:G2"
        body = {
            "values": [row_data]
        }
        
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

    except HttpError as err:
        # ログのエラーはメイン処理を止めないよう、控えめに表示するかコンソールに出す
        print(f"ログ記録APIエラー: {err}")
    except Exception as e:
        print(f"ログ記録予期せぬエラー: {e}")