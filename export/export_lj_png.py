
"""
Export biểu đồ Levey–Jennings thành PNG (bytes).
"""
from io import BytesIO
import pandas as pd
from .word_reports import build_lj_figure_from_z

def export_lj_png(z_df: pd.DataFrame, point_df=None) -> BytesIO:
    fig = build_lj_figure_from_z(z_df=z_df, point_df=point_df)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    return buf
