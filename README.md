# Phần mềm nội kiểm IQC – Tone Premium Warm Gold

Ứng dụng Streamlit nhiều trang để quản lý nội kiểm (IQC) cho xét nghiệm:

- Thiết lập chỉ số thống kê (X, SD, CV, CVh) cho từng mức QC.
- Nhập IQC hằng ngày, tính z-score, đánh giá quy tắc Westgard theo sigma.
- Vẽ biểu đồ Levey–Jennings (z-score) với đánh dấu vi phạm.
- Hỗ trợ **multi-analyte**: nhiều xét nghiệm trong cùng ứng dụng.
- Giao diện tone **premium vàng kem**, kèm icon nhỏ và khung **Quick actions**.

## Theme premium (JSON)

- Theme màu được quản lý tập trung ở file `assets/theme_premium.json`.
- Streamlit theme cơ bản nằm ở `.streamlit/config.toml`.
- `qc_core.inject_global_css()` đọc JSON và áp CSS để đảm bảo **không còn màu lạc tông**.

## Cách chạy

```bash
pip install -r requirements.txt
streamlit run app.py
```

Sau đó mở địa chỉ được hiển thị (thường là http://localhost:8501).

Thư mục `pages/` chứa các trang con:

1. `1_Thiet_lap_chi_so_thong_ke.py`
2. `2_Ghi_nhan_va_danh_gia.py`
3. `3_Bieu_do_Levey_Jennings.py`
4. `4_Huong_dan_va_About.py`


## Assets
- Logo: `assets/qc_logo.png` (đã kèm mẫu AquaSigma)
- Video minh hoạ: `assets/Lv-J.mp4`
