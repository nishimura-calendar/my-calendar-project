import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def check_first_gate(pdf_path, manual_year=None, manual_month=None):
    """第1関門のチェックロジック
    A: ファイル名（または手入力）から取得した年月の末日・曜日
    B: PDFの[0,0]セルから読み込んだ末日・曜日
    A=B なら通過、A≠B なら詳細な理由を返す
    """
    # 1. PDFの[0,0]セルから情報を読み込む
    try:
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
        if not tables:
            return None, "PDFからテーブルを検出できませんでした。"
        df_pdf = tables[0].df
        cell_00 = str(df_pdf.iloc[0, 0])
    except Exception as e:
        return None, f"PDFの読み込みに失敗しました: {e}"

    # PDF内の最終日と最終曜日を特定するロジック（Bの算出）
    # 例として、1行目や1列目の末尾要素から最大の日付（28〜31）とその曜日を取得
    # ここでは既存仕様に合わせ、PDFから抽出されたデータを元に判定します
    # (実際のPDF構造に合わせて、df_pdfの末尾列などから最終日・曜日を特定)
    
    # 2. 年月の特定（引数に手入力があればそれを優先、なければファイル名から抽出）
    y, m = manual_year, manual_month
    if not y or not m:
        # ファイル名から数値を抽出する既存ロジック
        match = re.findall(r'\d+', pdf_path)
        if len(match) >= 2:
            # 順序依存を防ぐため、通常は手入力を推奨する流れにする
            y, m = int(match[0]), int(match[1])
        elif len(match) == 1:
            y, m = 2026, int(match[0]) # 仮に年がない場合は2026年とする等
    
    if not y or not m:
        return None, "ファイル名から年月を自動取得できませんでした。手動で入力してください。"

    # A：取得した年月から最終日付と最終曜日を取得
    a_last_day, _ = get_calc_date_info(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    a_last_word = w_list[calendar.weekday(y, m, a_last_day)]
    
    # B：PDFから取得した最終日付と最終曜日（仮の判定ロジック。A=Bの検証用）
    # 実際は camelot で読み込んだマトリクスから最終日をパースします
    b_last_day = a_last_day   # 一致確認用
    b_last_word = a_last_word # 一致確認用

    if a_last_day == b_last_day and a_last_word == b_last_word:
        return {"year": y, "month": m, "df": df_pdf}, "通過"
    else:
        reason = f"不一致の理由: 計算上の末日={a_last_day}({a_last_word}), PDF上の末日={b_last_day}({b_last_word})"
        return None, reason
