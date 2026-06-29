import streamlit as st
import camelot
import re
import calendar

def check_pdf_consistency_with_anchors(pdf_path, year, month):
    try:
        # 表の構造を無視して全ページ読み込み
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
        # 全セルを結合して巨大な文字列を作成
        full_text = " ".join([cell for table in tables for row in table.df.values for cell in row])
        
        # 1. 正規表現で「数字」と「曜日」のペアを強制抽出
        # \d{1,2} で日付、\s*で間の空白（改行含む）、[日月火水木金土]で曜日をキャプチャ
        pattern = r'(\d{1,2})\s*([日月火水木金土])'
        matches = re.findall(pattern, full_text)
        
        # 2. 辞書化（重複排除。同じ日付が複数箇所にあってもOK）
        day_map = {int(day): wd for day, wd in matches}
        sorted_days = sorted(day_map.keys())
        
        # 3. 理論値との比較
        _, last_day_expected = calendar.monthrange(year, month)
        
        # 検証1: 日付が不足していないか
        if len(sorted_days) < last_day_expected:
            return False, f"抽出失敗: {len(sorted_days)}日しか特定できませんでした。リスト: {sorted_days}", None

        # 検証2: 最終日の曜日がカレンダーと一致するか
        last_day = sorted_days[-1]
        found_weekday = day_map[last_day]
        theory_weekday_idx = calendar.weekday(year, month, last_day)
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        
        if jp_weekdays[theory_weekday_idx] != found_weekday:
            return False, f"曜日不一致: 最終日の{last_day}日はカレンダー上「{jp_weekdays[theory_weekday_idx]}」ですが、PDFからは「{found_weekday}」が抽出されました。", day_map
        
        return True, "第1関門突破！整合性OKです。", day_map

    except Exception as e:
        return False, f"解析エラー: {e}", None

# --- メイン処理イメージ ---
# 実行ボタンが押されたとき:
# is_success, msg, data = check_pdf_consistency_with_anchors(temp_path, year, month)
# if is_success:
#     st.success(msg)
# else:
#     st.error(msg)
