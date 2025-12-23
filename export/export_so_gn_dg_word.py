"""
Export Sổ ghi nhận & đánh giá ra Word (A4), có biểu đồ LJ giống trên app.
"""
from io import BytesIO
import pandas as pd
from .word_reports import ReportMeta, build_so_ghi_nhan_3muc_docx, build_so_ghi_nhan_2muc_docx

def export_so_gn_dg(meta: ReportMeta, export_df: pd.DataFrame, z_df: pd.DataFrame, point_df=None, num_levels: int = 3) -> BytesIO:
    if int(num_levels) == 2:
        return build_so_ghi_nhan_2muc_docx(export_df=export_df, z_df=z_df, meta=meta, point_df=point_df)
    return build_so_ghi_nhan_3muc_docx(export_df=export_df, z_df=z_df, meta=meta, point_df=point_df)
