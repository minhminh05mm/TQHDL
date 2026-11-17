# Phân tích giá thuê nhà ở Hà Nội với PostgreSQL

## Dữ liệu và quy trình

Hai đầu vào giữ nguyên tên: `raw/phongtro123_raw.csv` và `raw/house_rental_dec29th_2025.csv`. Quy trình `etl.py` đọc nguồn, chuẩn hóa riêng, kết hợp và nạp PostgreSQL. Các CSV sạch và `combined.csv` vẫn được xuất để đối chiếu; Streamlit và notebook đọc PostgreSQL, không dùng CSV làm nguồn dự phòng.

Nguồn: [Phongtro123 Hà Nội](https://phongtro123.com/tinh-thanh/ha-noi) và [Vietnam Real Estate Datasets – Catalyst](https://www.kaggle.com/datasets/cresht2606/vietnam-real-estate-datasets-catalyst), bản chụp Catalyst ngày 29/12/2025.

| Nguồn | Raw | Sau làm sạch riêng | Nạp DB |
|---|---:|---:|---:|
| Phongtro123 | 2.983 | 1.859 | 1.859 |
| Catalyst | 4.808 | 1.321 | 1.168 |
| Tổng | 7.791 | 3.180 | 3.027 |

Mỗi dòng raw có vị trí file, nội dung gốc và kết quả xử lý. Tổng 4.764 dòng nằm ngoài phạm vi hoặc chưa đủ loại/mục đích thuê để đưa vào bảng chung. Bảng vận hành có 51 giá thuê thiếu, 166 diện tích thiếu, 193 giá/m² thiếu; 2.834 tin đủ giá và diện tích. Notebook loại diện tích thiếu, còn 2.861 tin.

## Cấu trúc

| Tệp/thư mục | Vai trò |
|---|---|
| `extract/extract.py` | Đọc/kiểm tra hai nguồn; tùy chọn thu thập Phongtro123 |
| `raw` | CSV đầu vào giữ nguyên |
| `transform/transform.py` | Quy tắc giá, diện tích, loại chỗ ở, mục đích và địa bàn |
| `transform/*_clean.csv`, `transform/combined.csv` | Kết quả trung gian và đối chiếu |
| `etl.py` | Điều phối, checksum, dấu vết từng dòng, kiểm tra và nạp dữ liệu |
| `db/schema.sql` | Chín bảng và các view PostgreSQL trong schema `rentals` |
| `db/client.py` | Cấu hình kết nối và đọc dữ liệu |
| `db/load.py` | Staging, Load và đối chiếu DB với kết quả Transform |
| `db/local_postgres.py` | Tạo/chạy/dừng PostgreSQL riêng trên máy cục bộ |
| `bi/dashboard.py` | Dashboard và gợi ý thuê từ DB |
| `bi/B23DCKD034_Pham Minh Khanh_TQHDL.ipynb` | Notebook đọc DB, 32 ô code, 10 biểu đồ |
| `tests/test_postgres.py` | Kiểm thử dữ liệu, truy vết, ràng buộc, rollback và dashboard |
| `.env.example` | Mẫu cấu hình riêng cho từng máy |
| `requirements.txt`, `requirements-lock.txt` | Thư viện chính và các phiên bản phụ thuộc đã kiểm tra |
| `report` | Thiết kế DB, cách chạy và chuyển máy |

## Thực thi

Windows cài Python 3.11 và PostgreSQL. Chạy lần lượt `setup_windows.bat`, `chay_etl.bat`, `chay_dashboard.bat`. Dashboard mở ở cổng 8502. `dung_postgres.bat` dừng cluster của dự án; không tác động dịch vụ PostgreSQL khác.

Các lệnh tương đương, từ thư mục gốc:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe db/local_postgres.py start
.\.venv\Scripts\python.exe etl.py
.\.venv\Scripts\python.exe -m streamlit run bi/dashboard.py --server.port 8502
```

`python etl.py --force` tạo một lần xử lý mới ngay cả khi raw không đổi. Mặc định, checksum raw và phiên bản quy tắc giống lần thành công hiện tại thì dùng lại lần đó, không nhân đôi dữ liệu. `--crawl` chủ động thu thập lại Phongtro123; chế độ mặc định tái hiện kết quả từ hai raw có sẵn, không crawl.

## Cập nhật

Dashboard kiểm tra lần ETL thành công mới nhất mỗi 10 giây khi phiên hoạt động. Sau khi ETL commit thành công, phiên tự nạp dữ liệu mới và tính lại biểu đồ. Thay CSV riêng lẻ hoặc tải lại trình duyệt không thay thế việc chạy ETL.

Một giao dịch nạp cuối gồm tin sạch, kết quả từng dòng và trạng thái thành công. Nếu Load/kiểm tra lỗi thì giao dịch rollback, lần chạy có trạng thái thất bại và dashboard tiếp tục dùng lần thành công trước. Staging của lần lỗi vẫn được giữ để đối chiếu. Có khóa điều phối để hai tiến trình ETL không nạp đồng thời.

## Giới hạn

Đơn vị quan sát là tin đăng và giá chào thuê. Không xác nhận giao dịch hoặc tình trạng còn trống. Nhãn thời gian không được coi là ngày đăng đầu tiên. Không gán phường/xã mới khi thiếu căn cứ; quận/huyện lịch sử vẫn là hệ phân nhóm chung. Các nhóm nghi trùng của dashboard chỉ được đánh dấu, không tự xóa.
