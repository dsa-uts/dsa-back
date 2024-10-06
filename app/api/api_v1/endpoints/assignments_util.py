import pandas as pd
from pathlib import Path
import io


def get_report_list(report_list_path: Path) -> pd.DataFrame | None:
    '''
    reportlist.xlsx(またはreportlist.xls)を読み込み、
    "# 学籍番号", "# ロール", "# 提出", "# 提出日時"の4列のみを取得する
    '''
    
    if report_list_path.suffix != ".xlsx" and report_list_path.suffix != ".xls":
        return None
    
    # エクセルファイルを読み込む
    df = pd.read_excel(report_list_path, header=None)
    
    # CSVに変換
    csv_str = df.to_csv(index=False)
    data_io = io.StringIO(csv_str)
    
    # 最初から、"# 内部コースID"で始まる箇所まで削除(pandasではなく、csvを直接操作する)
    data_io.seek(0)
    lines = data_io.readlines()
    lines = [line.strip() for line in lines]
    for i, line in enumerate(lines):
        if line.startswith("# 内部コースID"):
            break
    lines = lines[i:]
    
    # "#end"で始まる行を見つけて、それ以降の行を削除
    end_row = 0
    for i, line in enumerate(lines):
        if line.startswith("#end"):
            end_row = i
            break
    lines = lines[:end_row]
    
    # print("first transform")
    # for line in lines:
    #     print(line)
    
    csv_str = "\n".join(lines)
    data_io = io.StringIO(csv_str)
    
    df = pd.read_csv(data_io)
    
    columes_to_keep = ["# 学籍番号", "# ロール", "# 提出", "# 提出日時"]
    df = df[columes_to_keep]
    
    return df
