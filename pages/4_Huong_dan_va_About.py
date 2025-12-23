import streamlit as st

import qc_core as qc


qc.apply_page_config()
qc.inject_global_css()
cfg = qc.render_sidebar()

sigma_cat, active_rules = qc.get_sigma_category_and_rules(
    cfg["sigma_value"], cfg["num_levels"]
)

qc.render_global_header()
qc.render_top_info_cards(cfg, sigma_cat, active_rules)

st.subheader("4️⃣ 📘 Hướng dẫn sử dụng & About")

st.markdown("### 📚 Quy trình thao tác gợi ý")

st.markdown(
    """
1. **🧮 Thiết lập chỉ số thống kê (trang 1)**  
   - Chạy lặp mẫu QC (ít nhất 20 lần) cho từng mức.  
   - Nhập dữ liệu vào bảng `Ctrl 1`, `Ctrl 2`, `Ctrl 3`.  
   - App tính `Mean, SD, CV%` và cho phép nhập `CVh` để tính `SD theo CVh`.  

2. **✏️ Nhập IQC hằng ngày & đánh giá Westgard (trang 2)**  
   - Chọn dùng **SD thực nghiệm** hay **SD theo CVh** để tính z-score.  
   - Nhập kết quả nội kiểm từng ngày cho các mức QC.  
   - Ứng dụng sẽ:
     - Tính z-score.  
     - Áp dụng bộ **quy tắc Westgard theo sigma**.  
     - Đưa ra trạng thái Đạt / Cảnh báo / Không đạt.  
     - Cho phép tải file Excel **"Sổ theo dõi KQ NK"**.

3. **📊 Theo dõi biểu đồ Levey–Jennings (trang 3)**  
   - App chuyển bảng z-score thành biểu đồ Levey–Jennings dạng z-score.  
   - Các điểm vi phạm được **khoanh đỏ** và gắn mã quy tắc ngay trên đồ thị.  
   - Đường ±3.5SD màu đen gạch đứt thể hiện các z-score vượt ±3SD.

4. **🧬 Quản lý nhiều xét nghiệm (multi-analyte)**  
   - Ở sidebar, chị có thể:
     - Chọn xét nghiệm đang làm việc trong danh sách.  
     - Hoặc bấm **"➕ Thêm xét nghiệm mới"** để tạo thêm.  
   - Mỗi xét nghiệm được lưu riêng:
     - Thông tin cấu hình (thiết bị, phương pháp, QC...).  
     - Bảng thiết lập thống kê.  
     - Bảng IQC hằng ngày, z-score, Westgard, biểu đồ.  

5. **🎨 Tuỳ chỉnh giao diện**  
   - Thêm logo labo vào `assets/qc_logo.png`.  
   - Thêm hình minh hoạ Levey–Jennings vào `assets/levey_jennings_demo.png`.  
   - Nếu muốn đổi màu tone aqua → chỉnh biến màu trong file `qc_core.py` phần CSS.
"""
)

st.markdown("### ℹ️ About")

st.markdown(
    """
**Phần mềm nội kiểm IQC – tone Aqua**  
- Giao diện: **sang trọng, hiện đại, icon rõ ràng, ít chữ, nhiều trực quan**.  
- Thiết kế để mô phỏng sát file Excel nội kiểm, nhưng tiện lợi hơn trên web:  
  - Tự động tính toán & lưu trạng thái cho từng xét nghiệm.  
  - Có thể triển khai trên **Streamlit Cloud** để dùng cho nhiều máy trong labo.  

Nếu chị muốn mở rộng thêm:
- Trang **Phân tích xu hướng bias/shift** theo thời gian,  
- Trang **Gợi ý hành động khắc phục** khi QC không đạt,  

thì có thể tiếp tục bổ sung vào thư mục `pages/` với cùng phong cách giao diện.
"""
)
