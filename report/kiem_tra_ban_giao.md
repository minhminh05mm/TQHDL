# Kết quả kiểm tra PostgreSQL

Ngày kiểm tra: 18/11/2026.

- PostgreSQL 18, database `btl_tqhdl`, schema `rentals`, tài khoản `btl_app` không mật khẩu ở `127.0.0.1:5433`.
- Chín bảng lưu ETL, raw, kết quả từng dòng, danh mục và tin sạch. Dashboard dùng 3.027 tin của lần thành công mới nhất.
- Nạp 7.791 dòng raw, có kết quả xử lý từng dòng; 3.027 tin giữ lại và 4.764 dòng ngoài phạm vi/không đủ điều kiện gộp.
- Đối chiếu toàn bộ 15 cột và 3.027 dòng giữa Transform và DB, bao gồm giá thiếu, diện tích thiếu và đơn giá.
- Chạy lại cùng raw và quy tắc không tạo thêm lần nạp thành công hoặc nhân đôi tin.
- Thử lỗi sau khi ghi các tin sạch nhưng trước commit: Load rollback, dashboard vẫn dùng lần thành công trước; trạng thái thất bại và staging được giữ.
- Kiểm tra kiểu giá, liên kết rỗng, khóa ngoại và giá/m² không khớp: PostgreSQL từ chối dữ liệu không hợp lệ.
- Streamlit đọc DB, hiển thị đủ biểu đồ, lọc nguồn và cập nhật phiên bản sau một lần ETL mới. Gợi ý mặc định có 1.309 tin.
- Chặn thao tác `pandas.read_csv` trong kiểm thử dashboard để xác minh ứng dụng không dùng CSV dự phòng.
- Notebook được chạy lại từ đầu bằng môi trường mới: 32 ô code, 10 hình; 2.861 tin sau bỏ diện tích thiếu và 2.834 tin đủ giá/diện tích. Nhận xét đã cập nhật theo số liệu mới.
- Cài thư viện từ requirements trong môi trường Python riêng; có file khóa phiên bản phụ thuộc và không có xung đột khi kiểm tra pip.
- Tạo lại database từ raw tại thư mục bàn giao khác với thư mục phát triển để kiểm tra đường dẫn tương đối và khởi tạo PostgreSQL mới.
- Hai CSV raw giữ nguyên checksum; các tên CSV và tên notebook được giữ nguyên. Hai phiên bản dự án trước cùng báo cáo Word/PDF không bị sửa.

Các kiểm thử có thể chạy lại bằng `python -m unittest discover -s tests -v`. Chúng tạo thêm lịch sử ETL và một lần thất bại giả lập; đây là phép kiểm tra rollback, không phải lỗi dữ liệu của lần đang vận hành.
