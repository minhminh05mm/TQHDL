CREATE SCHEMA IF NOT EXISTS rentals;

CREATE TABLE IF NOT EXISTS rentals.sources (
    source_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE CHECK (btrim(source_name) <> ''),
    source_url TEXT NOT NULL CHECK (btrim(source_url) <> '')
);

CREATE TABLE IF NOT EXISTS rentals.etl_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','success','failed')),
    input_fingerprint CHAR(64) NOT NULL,
    rules_version CHAR(64) NOT NULL,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    CHECK ((status='running' AND finished_at IS NULL) OR
           (status IN ('success','failed') AND finished_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS rentals.input_files (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES rentals.etl_runs,
    source_id SMALLINT NOT NULL REFERENCES rentals.sources,
    filename TEXT NOT NULL CHECK (btrim(filename) <> ''),
    sha256 CHAR(64) NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, source_id),
    UNIQUE (file_id, run_id)
);

CREATE TABLE IF NOT EXISTS rentals.raw_listings (
    raw_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL,
    file_id BIGINT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number >= 1),
    source_listing_id TEXT,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload)='object'),
    FOREIGN KEY (file_id,run_id) REFERENCES rentals.input_files(file_id,run_id),
    UNIQUE (file_id,row_number),
    UNIQUE (raw_id,run_id)
);

CREATE TABLE IF NOT EXISTS rentals.districts (
    district_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    old_district_name TEXT NOT NULL UNIQUE CHECK (btrim(old_district_name)<>'')
);
CREATE TABLE IF NOT EXISTS rentals.wards (
    ward_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    current_ward_name TEXT NOT NULL UNIQUE CHECK (btrim(current_ward_name)<>'')
);
CREATE TABLE IF NOT EXISTS rentals.housing_types (
    housing_type_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    housing_type_name TEXT NOT NULL UNIQUE
        CHECK (housing_type_name IN ('phòng trọ','căn hộ','nhà nguyên căn','biệt thự'))
);

CREATE TABLE IF NOT EXISTS rentals.rental_listings (
    listing_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES rentals.etl_runs,
    raw_id BIGINT NOT NULL,
    import_position INTEGER NOT NULL CHECK (import_position>=1),
    source_id SMALLINT NOT NULL REFERENCES rentals.sources,
    source_listing_id TEXT NOT NULL CHECK (btrim(source_listing_id)<>''),
    source_url TEXT NOT NULL CHECK (source_url ~ '^https?://'),
    title TEXT NOT NULL CHECK (btrim(title)<>''),
    district_id SMALLINT NOT NULL REFERENCES rentals.districts,
    mentioned_ward TEXT,
    ward_id SMALLINT REFERENCES rentals.wards,
    ward_resolution_status TEXT NOT NULL,
    housing_type_id SMALLINT NOT NULL REFERENCES rentals.housing_types,
    rental_purpose TEXT NOT NULL CHECK (rental_purpose IN ('để ở','ở và kinh doanh')),
    area_m2 DOUBLE PRECISION CHECK (area_m2 IS NULL OR area_m2 BETWEEN 5 AND 1000),
    price_status TEXT NOT NULL,
    area_status TEXT NOT NULL,
    monthly_price_vnd BIGINT CHECK (monthly_price_vnd IS NULL OR monthly_price_vnd BETWEEN 500000 AND 500000000),
    unit_price_vnd_m2 BIGINT CHECK (unit_price_vnd_m2 IS NULL OR unit_price_vnd_m2>0),
    FOREIGN KEY (raw_id,run_id) REFERENCES rentals.raw_listings(raw_id,run_id),
    UNIQUE (run_id,source_id,source_listing_id),
    UNIQUE (run_id,source_url),
    UNIQUE (run_id,import_position),
    UNIQUE (run_id,raw_id),
    UNIQUE (listing_id,run_id,raw_id),
    CHECK ((monthly_price_vnd IS NULL OR area_m2 IS NULL) = (unit_price_vnd_m2 IS NULL)),
    CHECK (unit_price_vnd_m2 IS NULL OR abs(unit_price_vnd_m2-monthly_price_vnd::numeric/area_m2::numeric)<=1)
);

CREATE TABLE IF NOT EXISTS rentals.etl_row_results (
    run_id BIGINT NOT NULL REFERENCES rentals.etl_runs,
    raw_id BIGINT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('loaded','excluded')),
    stage TEXT NOT NULL CHECK (stage IN ('scope','clean','combine','load')),
    reason_code TEXT NOT NULL CHECK (btrim(reason_code)<>''),
    cleaned BOOLEAN NOT NULL DEFAULT FALSE,
    quality JSONB NOT NULL DEFAULT '{}'::jsonb,
    listing_id BIGINT,
    PRIMARY KEY (run_id,raw_id),
    FOREIGN KEY (raw_id,run_id) REFERENCES rentals.raw_listings(raw_id,run_id),
    FOREIGN KEY (listing_id,run_id,raw_id) REFERENCES rentals.rental_listings(listing_id,run_id,raw_id),
    CHECK ((decision='loaded')=(listing_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS listings_type_district_price ON rentals.rental_listings(run_id,housing_type_id,district_id,monthly_price_vnd);
CREATE INDEX IF NOT EXISTS listings_ward_price_area ON rentals.rental_listings(run_id,ward_id,monthly_price_vnd,area_m2);
CREATE INDEX IF NOT EXISTS listings_source ON rentals.rental_listings(run_id,source_id);
CREATE INDEX IF NOT EXISTS results_reasons ON rentals.etl_row_results(run_id,decision,reason_code);

CREATE OR REPLACE VIEW rentals.v_current_run AS
SELECT run_id, started_at, finished_at, summary FROM rentals.etl_runs
WHERE status='success' ORDER BY run_id DESC LIMIT 1;

CREATE OR REPLACE VIEW rentals.v_all_listings AS
SELECT l.run_id AS etl_run_id, l.import_position,
    s.source_name AS "Nguồn", l.source_listing_id AS "Mã tin",
    l.source_url AS "Liên kết tin gốc", l.title AS "Tiêu đề",
    d.old_district_name AS "Quận/huyện cũ", l.mentioned_ward AS "Phường/xã được nêu",
    w.current_ward_name AS "Phường/xã mới", l.ward_resolution_status AS "Trạng thái xác định phường/xã",
    h.housing_type_name AS "Loại chỗ ở", l.rental_purpose AS "Mục đích thuê",
    l.area_m2 AS "Diện tích (m²)", l.price_status AS "Trạng thái giá",
    l.area_status AS "Trạng thái diện tích", l.monthly_price_vnd AS "Giá thuê (đồng/tháng)",
    l.unit_price_vnd_m2 AS "Giá thuê/m² (đồng/tháng)"
FROM rentals.rental_listings l
JOIN rentals.sources s USING(source_id)
JOIN rentals.districts d USING(district_id)
LEFT JOIN rentals.wards w USING(ward_id)
JOIN rentals.housing_types h USING(housing_type_id);

CREATE OR REPLACE VIEW rentals.v_dashboard_listings AS
SELECT a."Nguồn",a."Mã tin",a."Liên kết tin gốc",a."Tiêu đề",a."Quận/huyện cũ",
       a."Phường/xã được nêu",a."Phường/xã mới",a."Trạng thái xác định phường/xã",
       a."Loại chỗ ở",a."Mục đích thuê",a."Diện tích (m²)",a."Trạng thái giá",
       a."Trạng thái diện tích",a."Giá thuê (đồng/tháng)",a."Giá thuê/m² (đồng/tháng)"
FROM rentals.v_all_listings a JOIN rentals.v_current_run r ON a.etl_run_id=r.run_id
ORDER BY a.import_position;

CREATE OR REPLACE VIEW rentals.v_notebook_listings AS
SELECT * FROM rentals.v_dashboard_listings WHERE "Diện tích (m²)" IS NOT NULL;

CREATE OR REPLACE VIEW rentals.v_etl_summary AS
SELECT f.run_id,s.source_name,f.filename,f.sha256,f.row_count AS raw_rows,
       count(e.raw_id) AS processed_rows,
       count(*) FILTER (WHERE e.cleaned) AS clean_rows,
       count(*) FILTER (WHERE e.decision='loaded') AS loaded_rows,
       count(*) FILTER (WHERE e.decision='excluded') AS excluded_rows
FROM rentals.input_files f JOIN rentals.sources s USING(source_id)
LEFT JOIN rentals.raw_listings raw USING(file_id,run_id)
LEFT JOIN rentals.etl_row_results e USING(raw_id,run_id)
GROUP BY f.file_id,f.run_id,s.source_name,f.filename,f.sha256,f.row_count;

CREATE OR REPLACE VIEW rentals.v_lineage AS
SELECT e.run_id,s.source_name,f.filename,raw.row_number,raw.source_listing_id,
       e.decision,e.stage,e.reason_code,e.cleaned,e.quality,e.listing_id,raw.payload
FROM rentals.etl_row_results e
JOIN rentals.raw_listings raw USING(raw_id,run_id)
JOIN rentals.input_files f USING(file_id,run_id)
JOIN rentals.sources s USING(source_id);

CREATE OR REPLACE VIEW rentals.v_data_quality_summary AS
SELECT count(*) AS total_listings,
       count(*) FILTER (WHERE "Giá thuê (đồng/tháng)" IS NULL) AS missing_price,
       count(*) FILTER (WHERE "Diện tích (m²)" IS NULL) AS missing_area,
       count(*) FILTER (WHERE "Giá thuê/m² (đồng/tháng)" IS NULL) AS missing_unit_price,
       count(*) FILTER (WHERE "Phường/xã mới" IS NULL) AS unresolved_current_ward,
       count(*) FILTER (WHERE "Giá thuê (đồng/tháng)">0 AND "Diện tích (m²)" >0) AS complete_price_area
FROM rentals.v_dashboard_listings;

CREATE OR REPLACE VIEW rentals.v_district_type_medians AS
SELECT "Quận/huyện cũ" AS old_district_name,"Loại chỗ ở" AS housing_type_name,
       count(*) AS listing_count,
       percentile_cont(.5) WITHIN GROUP(ORDER BY "Giá thuê (đồng/tháng)") AS median_price_vnd
FROM rentals.v_dashboard_listings WHERE "Giá thuê (đồng/tháng)" >0
GROUP BY "Quận/huyện cũ","Loại chỗ ở";
