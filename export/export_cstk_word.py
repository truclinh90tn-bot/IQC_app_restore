"""
Export Phiếu thiết lập CSTK ra Word (A4), gồm header/footer theo form.
"""
from io import BytesIO
import pandas as pd
from .word_reports import ReportMeta, build_cstk_3muc_docx, build_cstk_2muc_docx

def export_cstk(meta: ReportMeta, stats_df: pd.DataFrame, raw_df=None, num_levels: int = 3) -> BytesIO:
    if int(num_levels) == 2:
        return build_cstk_2muc_docx(meta=meta, raw_df=raw_df, stats_df=stats_df)
    return build_cstk_3muc_docx(meta=meta, raw_df=raw_df, stats_df=stats_df)
