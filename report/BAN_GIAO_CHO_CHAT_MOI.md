# Bàn giao dự án cho chat trên máy khác

Cập nhật ngày 18/11/2026. Đây là tài liệu bàn giao công việc và trạng thái thực tế, không phải nội dung để chép nguyên vào báo cáo nộp giảng viên.

## 1. Yêu cầu đang thực hiện

Dự án phân tích giá chào thuê nhà ở Hà Nội phải trình bày đầy đủ Extract, Transform, Load, thiết kế PostgreSQL và dashboard Streamlit đọc DB. Phần cần làm tiếp là lấy ảnh schema/ERD thực tế và chuẩn bị nội dung báo cáo/bảo vệ về nguồn, phương pháp xử lý và kiến trúc.

Đọc theo thứ tự:

1. Tệp này để biết trạng thái và phần còn thiếu.
2. `report/readme_chuyen_may.md` để cài đặt và kết nối.
3. `report/readme_postgres.md` để nắm luồng chạy.
4. `report/thiet_ke_database.md`, `db/schema.sql`, `etl.py`, `db/load.py`, `bi/dashboard.py` để đối chiếu mô tả với code thật.

Repo: https://github.com/minhminh05mm/TQHDL

## 2. Những gì có trong repo

Đây là toàn bộ bản dự án PostgreSQL có thể chạy lại, không chỉ riêng mã ETL:

| Thành phần | Tệp/thư mục |
|---|---|
| Thu thập/kiểm tra nguồn | `extract/extract.py` |
| Hai dữ liệu raw | `raw/phongtro123_raw.csv`, `raw/house_rental_dec29th_2025.csv` |
| Làm sạch và gộp | `transform/transform.py` và ba CSV đầu ra |
| Điều phối ETL | `etl.py` |
| PostgreSQL | `db/schema.sql`, `db/client.py`, `db/load.py`, `db/local_postgres.py`, `db/queries_for_report.sql` |
| Streamlit | `bi/dashboard.py`, `bi/analysis_utils.py` |
| Notebook | `bi/B23DCKD034_Pham Minh Khanh_TQHDL.ipynb` |
| Thư viện và cấu hình | `requirements.txt`, `requirements-lock.txt`, `.env.example` |
| Cách chạy Windows | `setup_windows.bat`, `chay_etl.bat`, `chay_dashboard.bat`, `dung_postgres.bat` |
| Kiểm thử | `tests/test_postgres.py` |
| Báo cáo cũ | `report/PHẠM MINH KHÁNH - B23DCKD034.pdf` |

`.venv`, `.postgres`, `.env`, log và cache không được đưa lên GitHub. Máy đích phải tạo lại môi trường và DB. Repo không có tệp `.docx`: bản nguồn gần nhất chỉ có PDF. Không tự nhận rằng Word gốc đã được bàn giao.

PDF được chép nguyên nội dung từ phiên bản trước, chưa cập nhật phần PostgreSQL/ETL. Giữ nguyên tên notebook và các CSV vì đã được tham chiếu trong báo cáo. Không sửa Word/PDF hiện có nếu chưa được người dùng yêu cầu.

## 3. Cấu hình và dữ liệu đã kiểm tra

Trên máy đã triển khai: PostgreSQL 18.6, host `127.0.0.1`, cổng `5433`, database `btl_tqhdl`, schema `rentals`, user `btl_app`, mật khẩu trống. Đây là cluster riêng của dự án, không phải dịch vụ PostgreSQL mặc định ở cổng 5432.

Máy khác không được giả định các dịch vụ hoặc đường dẫn cài đặt giống máy cũ. Đọc `.env.example`; chọn chế độ local riêng hoặc server có sẵn như hướng dẫn. Không sửa xác thực hoặc database của dự án khác.

Số liệu tham chiếu trên hai raw đang kèm repo:

| Chỉ tiêu | Phongtro123 | Catalyst | Tổng |
|---|---:|---:|---:|
| Raw | 2.983 | 4.808 | 7.791 |
| Sau clean riêng | 1.859 | 1.321 | 3.180 |
| Vào view dashboard | 1.859 | 1.168 | 3.027 |

Catalyst có 1.889 tin Hà Nội trước làm sạch. Có 4.764 dòng raw ngoài phạm vi hoặc không đủ điều kiện đưa vào bảng chung. Bảng vận hành có 51 giá thiếu, 166 diện tích thiếu, 193 đơn giá thiếu; 2.834 tin đủ giá và diện tích. Notebook bỏ diện tích thiếu, còn 2.861 tin, vẫn giữ 27 giá thuê thiếu và 27 giá/m² thiếu.

Đã chạy 7 kiểm thử thành công, notebook 32 ô code và 10 biểu đồ. Gợi ý thuê mặc định có 1.309 tin. Đây là trạng thái trên máy cũ; chat mới phải chạy lại và xác minh trên máy đích trước khi tuyên bố đã kiểm tra.

Số lần chạy `run_id` thay đổi theo máy và lịch sử. Không cố định `run_id=4` hoặc sao chép số dòng vật lý của bảng lịch sử làm số tin đang vận hành. Dùng `rentals.v_current_run` và các view của lần thành công mới nhất.

## 4. Phần còn thiếu bắt buộc làm tiếp

**Chưa có ảnh schema/ERD pgAdmin hợp lệ của dự án trong bản bàn giao này.** Lần thao tác lấy ảnh trước đã bị dừng, chưa hoàn tất đăng ký kết nối hoặc xuất ảnh. Không đánh dấu mục này là xong chỉ vì đã có `schema.sql`, Mermaid hoặc database đang chạy.

Người dùng yêu cầu AI mới lấy ảnh schema, ERD **thực tế từ PostgreSQL để làm báo cáo, không bịa**. Thực hiện như sau:

1. Cài môi trường, khởi động PostgreSQL, chạy ETL và kiểm tra kết nối thật.
2. Mở pgAdmin hoặc DBeaver; đăng ký đúng host/cổng/database/user của máy đích. Không dùng một ERD đang mở sẵn của database khác.
3. Xác minh bằng truy vấn `current_database()`, `current_user`, `inet_server_port()` và kiểm tra schema `rentals`.
4. Chụp cây database/schema thể hiện `btl_tqhdl` → `rentals` → 9 bảng và 8 view. Tên database có thể khác nếu người dùng chủ động cấu hình; phải ghi đúng tên thực tế đó.
5. Tạo ERD bằng chức năng reverse engineer/generate ERD của **schema đang kết nối thật**. Trong pgAdmin, chọn schema `rentals` rồi dùng ERD For Schema. Kiểm tra đủ 9 bảng và 12 ràng buộc khóa ngoại; các FK ghép cần được giữ đúng.
6. Xuất PNG đủ độ phân giải; giữ tên bảng, cột, PK/FK và các quan hệ đọc được. Có thể xuất thêm ảnh chi tiết nhóm ETL và nhóm phân tích nếu toàn cảnh quá nhỏ.
7. Chụp kết quả SQL từ `v_etl_summary`, `v_data_quality_summary` và một ví dụ `v_lineage` để minh chứng số dòng và truy vết từ raw tới dữ liệu sạch.
8. Lưu ảnh vào `report/anh_minh_chung/`, ghi rõ công cụ, DB/schema, thời điểm lấy và truy vấn/chức năng tạo ảnh. Cập nhật danh sách minh chứng sau khi thực sự tạo xong.

### Quy tắc trung thực với ảnh và số liệu

- Không tự dựng một giao diện giống pgAdmin rồi gọi đó là ảnh chụp thật.
- Không dùng ảnh ERD/schema từ repo khác, database khác, SQLite hoặc ảnh tìm trên Internet.
- Không dùng ảnh vẽ bằng AI thay cho minh chứng PostgreSQL.
- Mermaid hoặc sơ đồ tự sinh từ metadata PostgreSQL có thể dùng để giải thích. Nếu dùng, ghi đúng là sơ đồ trích metadata; không gọi đó là ảnh chụp pgAdmin.
- Không chỉnh ảnh để thêm bảng, quan hệ, số liệu hoặc kết quả truy vấn chưa tồn tại.
- Nếu chưa kết nối được, thiếu công cụ hoặc không xuất ảnh được: báo rõ phần đang thiếu; không tuyên bố đã hoàn thành.
- Không suy giá thuê theo tháng, ngày đăng đầu tiên, số nhà độc lập hoặc tình trạng còn trống khi dữ liệu chưa chứng minh.

## 5. Các truy vấn lấy minh chứng

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port(), version();

SELECT tablename FROM pg_tables
WHERE schemaname='rentals' ORDER BY tablename;

SELECT viewname FROM pg_views
WHERE schemaname='rentals' ORDER BY viewname;

SELECT * FROM rentals.v_etl_summary
WHERE run_id=(SELECT run_id FROM rentals.v_current_run)
ORDER BY source_name;

SELECT * FROM rentals.v_data_quality_summary;

SELECT source_name, decision, stage, reason_code, COUNT(*) AS so_dong
FROM rentals.v_lineage
WHERE run_id=(SELECT run_id FROM rentals.v_current_run)
GROUP BY source_name, decision, stage, reason_code
ORDER BY source_name, stage, reason_code;

SELECT source_name, filename, row_number, source_listing_id, decision, reason_code, quality, payload
FROM rentals.v_lineage
WHERE run_id=(SELECT run_id FROM rentals.v_current_run)
  AND source_listing_id='671310';
```

Ví dụ tin Phongtro123 `671310`: raw ghi `4.2 triệu/tháng`, `30 m 2`; dữ liệu sạch là 4.200.000 đồng/tháng, 30 m², 140.000 đồng/m²/tháng. Vị trí raw trên bản kèm repo là dòng dữ liệu 1.816. Đây là ví dụ cần xác minh lại bằng SQL, không dùng như một ảnh kết quả có sẵn.

## 6. Nội dung cần chuẩn bị để bảo vệ

- **Nguồn:** Phongtro123 thu thập trực tiếp; Catalyst lấy trên Kaggle, bản chụp 29/12/2025, website gốc BatDongSan.vn theo mô tả bộ dữ liệu. Giữ liên kết nguồn, mã tin và file gốc.
- **Transform:** chọn phạm vi, loại tin bán/chỉ kinh doanh, phân loại nhà ở, chuẩn hóa đơn vị và địa bàn, kiểm tra thiếu/trùng/miền giá trị, tính giá/m², thống nhất 15 cột. Dữ liệu thiếu giá hoặc phường không được tự thay bằng 0/tên phỏng đoán.
- **Kiến trúc:** nguồn → raw CSV → staging PostgreSQL → Pandas Transform → transaction Load → view của lần thành công mới nhất → Streamlit. CSV clean/combined là đầu ra đối chiếu, không phải nguồn đọc dự phòng của dashboard.
- **DB:** 4 bảng theo dõi ETL, 4 bảng danh mục, 1 bảng tin sạch; quan hệ và kiểu dữ liệu phải khớp DB thực tế.
- **Độ tin cậy:** kiểm tra checksum và phiên bản quy tắc, chạy lại không nhân đôi, rollback khi Load lỗi, giữ trạng thái và dấu vết xử lý từng dòng.

## 7. Cách tiếp tục công việc

Sau clone/cài đặt, xác minh DB và ứng dụng trước. Ưu tiên hoàn tất ảnh minh chứng và phần giải thích; không viết lại code hoặc thiết kế DB khi chưa có lỗi cụ thể hay yêu cầu mới. Khi cần sửa, giữ code ngắn và không thêm lời nhắn cho AI vào notebook/code nộp. Mọi hướng dẫn cho chat chỉ nằm trong tệp bàn giao này.
