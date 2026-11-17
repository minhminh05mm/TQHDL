# Cấu hình PostgreSQL và chuyển dự án sang máy khác

## 1. Lấy dự án từ GitHub và đọc bàn giao

Repo chính: https://github.com/minhminh05mm/TQHDL

```powershell
git clone https://github.com/minhminh05mm/TQHDL.git
cd TQHDL
```

Nếu không dùng Git, chọn Code → Download ZIP trên GitHub, giải nén rồi mở đúng thư mục chứa `etl.py`, `raw`, `bi` và `requirements.txt`.

Chat trên máy mới cần đọc **`report/BAN_GIAO_CHO_CHAT_MOI.md` trước tiên**. Tệp đó ghi rõ phần nào đã chạy, phần nào còn thiếu và yêu cầu lấy ảnh schema/ERD thật từ PostgreSQL; không dùng ảnh giả hoặc schema của dự án khác.

## 2. Bộ chuyển máy

Dùng gói `BTL_TQHDL_POSTGRES.zip` hoặc chép mã nguồn, `raw`, `transform`, notebook, `report`, `tests`, `requirements.txt`, `requirements-lock.txt` và `.env.example`. Máy đích cần Python 3.11, PostgreSQL 16 trở lên và Internet khi cài thư viện lần đầu. Bộ đã được chạy kiểm tra với PostgreSQL 18.

Không chép `.venv`, `.postgres`, `.env`, cache và log từ máy cũ. Tạo môi trường, cấu hình và database trên máy đích. Đây là cách tái hiện toàn bộ ETL, không phụ thuộc đường dẫn ổ đĩa hay cụm PostgreSQL của máy cũ.

## 3. Chế độ mặc định không mật khẩu

```dotenv
POSTGRES_LOCAL=1
PGHOST=127.0.0.1
PGPORT=5433
PGDATABASE=btl_tqhdl
PGUSER=btl_app
PGPASSWORD=
PGSSLMODE=prefer
POSTGRES_BIN=
```

`db/local_postgres.py start` dùng các chương trình của PostgreSQL đã cài để tạo một cluster riêng tại `.postgres/data` trong thư mục dự án. Cluster này chỉ lắng nghe `127.0.0.1:5433`; tài khoản `btl_app` không mật khẩu chỉ được xác thực cho database `btl_tqhdl`. Tài khoản ứng dụng không có quyền superuser, tạo database hay tạo role. Một tài khoản quản trị cục bộ riêng `btl_owner` được dùng để khởi tạo cluster và database, không được dùng trong Streamlit.

Script không sửa `pg_hba.conf`, dịch vụ hoặc dữ liệu của PostgreSQL đang dùng cho các dự án khác. Database này là PostgreSQL thật; nó không nằm trong dịch vụ PostgreSQL mặc định ở cổng 5432. Trong pgAdmin, thêm kết nối `127.0.0.1`, cổng `5433`, maintenance database `btl_tqhdl`, user `btl_app`, mật khẩu trống để xem schema `rentals`.

Vị trí chương trình PostgreSQL được phát hiện từ PATH hoặc dịch vụ đã cài trên Windows. Nếu chưa tìm thấy, điền `POSTGRES_BIN` là thư mục chứa `pg_ctl.exe` và `initdb.exe`, ví dụ `C:/Program Files/PostgreSQL/18/bin`; hoặc dùng:

```powershell
.\.venv\Scripts\python.exe db/local_postgres.py start --bin "C:/Program Files/PostgreSQL/18/bin"
```

Thứ tự chạy trên máy mới:

1. Giải nén vào thư mục có quyền ghi.
2. Chạy `setup_windows.bat`; `.env` chỉ được tạo từ mẫu nếu chưa tồn tại.
3. Kiểm tra `.env`, chỉnh `POSTGRES_BIN` nếu cần.
4. Chạy `chay_etl.bat`: khởi động cluster, tạo role/database và xử lý dữ liệu từ raw.
5. Chạy `chay_dashboard.bat`; xem dashboard tại `http://localhost:8502`.
6. Mở notebook trong thư mục `bi` bằng kernel `.venv` của máy đích. Từ thư mục gốc có thể chạy:

```powershell
.\.venv\Scripts\python.exe -m jupyterlab "bi/B23DCKD034_Pham Minh Khanh_TQHDL.ipynb"
```

Chọn interpreter/kernel trong `.venv` vừa tạo, không dùng kernel trỏ tới đường dẫn của máy cũ.

Nếu cổng 5433 bận, chọn cổng khác trong `.env` trước lần tạo cluster đầu tiên. Khi cluster đã có, giữ nguyên tên DB, user và cổng đã khởi tạo. Muốn đổi các giá trị đó, dùng một bản giải nén mới với cấu hình mới. Không chép thư mục `.postgres` của máy khác vào bản mới.

## 4. Dùng một server PostgreSQL sẵn có

Chế độ này không khởi động cluster của dự án. Khai báo:

```dotenv
POSTGRES_LOCAL=0
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=btl_tqhdl
PGUSER=ten_tai_khoan
PGPASSWORD=mat_khau_tren_may_dich
PGSSLMODE=prefer
```

Database và role phải tồn tại, có quyền tạo schema/bảng trong database dự án. Một tài khoản có quyền CREATEDB có thể chạy `python etl.py --create-database` để tạo database chưa có. Nếu role không có quyền đó, quản trị viên tạo database trước rồi chạy `python etl.py`.

Mật khẩu rỗng chỉ kết nối được nếu server đã cấu hình phương thức xác thực phù hợp. Để dùng không mật khẩu tự động, chọn chế độ local ở mục 3. Không tự thay xác thực của server sẵn có. Với server từ xa, dùng hostname và chế độ SSL theo cấu hình của server, thường `PGSSLMODE=require` hoặc `verify-full` khi có chứng thư phù hợp.

Biến môi trường của tiến trình được ưu tiên hơn `.env`. Nếu máy có `PGHOST`, `PGPORT`, `PGUSER` hoặc `PGPASSWORD` đã khai báo toàn cục, kiểm tra chúng khi kết nối không đúng dự kiến. `.env` chứa cấu hình cục bộ, không đưa vào gói bàn giao; `.env.example` không có bí mật.

## 5. Chuyển cả lịch sử ETL

Chạy ETL từ raw trên máy mới tái tạo dữ liệu phân tích, nhưng không mang lịch sử các lần chạy của máy cũ. Nếu cần lịch sử, dùng công cụ PostgreSQL `pg_dump` và `pg_restore`, không chép thư mục dữ liệu vật lý.

Ví dụ PowerShell với bộ công cụ PostgreSQL 18:

```powershell
& "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe" -h 127.0.0.1 -p 5433 -U btl_app -d btl_tqhdl -Fc --no-owner --no-acl -f btl_tqhdl.dump
```

Trên máy mới, tạo cluster/database rỗng theo mục 3 trước. Sau đó:

```powershell
& "C:/Program Files/PostgreSQL/18/bin/pg_restore.exe" -h 127.0.0.1 -p 5433 -U btl_app -d btl_tqhdl --no-owner --no-acl --exit-on-error btl_tqhdl.dump
```

Restore vào database rỗng, không nạp đè database đã có bảng. Dùng bản công cụ tương thích với server; khuyến nghị hai máy cùng PostgreSQL 18 nếu chuyển dump. Cách chạy lại từ raw không cần dump.

## 6. Kiểm tra và minh chứng

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Các kiểm thử tạo thêm các lần ETL, gồm một lần thất bại giả lập để xác minh rollback. Dashboard chỉ chọn lần thành công mới nhất, không dùng các lần thất bại. File `requirements-lock.txt` ghi toàn bộ phiên bản thư viện đã kiểm tra trên Windows/Python 3.11; có thể cài trực tiếp từ file này khi cần tái hiện đúng môi trường.

Tài liệu kỹ thuật: [Psycopg 3](https://www.psycopg.org/psycopg3/docs/basic/usage.html), [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html).


## 7. Giao việc cho chat trên máy mới

Có thể gửi yêu cầu sau sau khi đã clone repo:

> Đọc `report/BAN_GIAO_CHO_CHAT_MOI.md`, `report/readme_chuyen_may.md` và code hiện tại. Giúp tôi cài dự án, xác minh PostgreSQL thật, chạy lại ETL/Streamlit rồi lấy ảnh schema và ERD thực tế từ pgAdmin/DBeaver để bổ sung báo cáo. Không bịa ảnh, số liệu, quan hệ hoặc tuyên bố đã kiểm tra khi chưa chạy được. Giữ nguyên tên CSV/notebook. Không sửa báo cáo Word/PDF khi tôi chưa yêu cầu.

Repo bao gồm dữ liệu, mã nguồn và notebook, cùng bản PDF cũ tại `report/PHẠM MINH KHÁNH - B23DCKD034.pdf`. PDF chưa cập nhật PostgreSQL/ETL. Hiện chưa có ảnh schema/ERD pgAdmin hợp lệ trong repo; chat mới phải lấy trên DB ở máy đích.
