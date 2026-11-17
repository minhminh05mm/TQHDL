SELECT * FROM rentals.v_etl_summary ORDER BY run_id,source_name;

SELECT run_id,status,started_at,finished_at,summary,error_message
FROM rentals.etl_runs ORDER BY run_id DESC;

SELECT source_name,decision,stage,reason_code,count(*) AS rows
FROM rentals.v_lineage WHERE run_id=(SELECT run_id FROM rentals.v_current_run)
GROUP BY source_name,decision,stage,reason_code ORDER BY source_name,stage,reason_code;

SELECT * FROM rentals.v_data_quality_summary;

SELECT * FROM rentals.v_district_type_medians
WHERE housing_type_name='phòng trọ' AND listing_count>=20
ORDER BY median_price_vnd;

SELECT "Nguồn","Mã tin","Tiêu đề","Quận/huyện cũ","Phường/xã mới",
       "Giá thuê (đồng/tháng)","Diện tích (m²)","Giá thuê/m² (đồng/tháng)","Liên kết tin gốc"
FROM rentals.v_dashboard_listings
WHERE "Loại chỗ ở"='phòng trọ' AND "Giá thuê (đồng/tháng)" BETWEEN 1 AND 5000000
  AND "Diện tích (m²)" >=20 AND "Giá thuê/m² (đồng/tháng)" >0
ORDER BY "Giá thuê/m² (đồng/tháng)","Diện tích (m²)"-20,"Giá thuê (đồng/tháng)","Nguồn","Mã tin"
LIMIT 50;

SELECT source_name,filename,row_number,source_listing_id,decision,reason_code,quality,payload
FROM rentals.v_lineage
WHERE run_id=(SELECT run_id FROM rentals.v_current_run) AND source_listing_id='671310';
