# GTI Control (Ingress UI) - Home Assistant Add-on

## Giới thiệu
Add-on này cho phép kết nối và điều khiển **biến tần hoà lưới GTI** trực tiếp từ Home Assistant.  
Bao gồm UI Ingress 3 tab (Thông số / Cài đặt / Lập lịch) và xuất entity qua **MQTT Discovery** để sử dụng trên card khác.

## Cài đặt
1. Clone hoặc fork repo này và push lên GitHub (public).  
2. Trong Home Assistant:  
   - Vào **Settings → Add-ons → Add-on Store → ⋮ → Repositories**  
   - Thêm URL repo GitHub của bạn (ví dụ `https://github.com/yourname/ha-addons`)  
   - Reload → sẽ thấy add-on **GTI Control (Ingress UI)** trong danh sách.  
3. Bấm Install → Start → Open Web UI.

## Tính năng
- **UI Ingress 3 tab**:
  - **Thông số**: xem realtime GTI / Grid / Tiêu thụ (bao gồm daily/monthly từ server).  
  - **Cài đặt**: chỉnh cutoff_voltage, max_power_limit.  
  - **Lập lịch**: cấu hình 3 lịch (start, end, cutoff, max power).  
- **Entity HA**: tất cả thông số & điều khiển cũng được publish ra MQTT Discovery.  
- **Tùy chọn**:
  - `server_enabled`: bật/tắt hoàn toàn server.  
  - `use_server_daily_monthly`: bật/tắt việc lấy daily/monthly từ server.  
  - `expose_totals_only`: chỉ xuất total + tức thời (ẩn daily/monthly).  

## Cấu hình Add-on
Vào tab **Configuration** khi cài add-on, các tùy chọn chính:  
- `auth_method`: email_password | google  
- `email`, `password`: thông tin đăng nhập nếu dùng email/password  
- `server_enabled`: true/false (mặc định true)  
- `use_server_daily_monthly`: true/false (mặc định true)  
- `expose_totals_only`: true/false  
- `server_base_url`: URL server (mặc định https://giabao-inverter.com)  
- `firebase_api_key`, `firebase_project_id`: nếu dùng Firebase login  
- `mqtt_device_source`: mqtt | rest  
- `device_mqtt_host`, `device_mqtt_port`, `device_mqtt_username`, `device_mqtt_password`  
- `publish_mqtt`: true/false  
- `mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password`, `mqtt_prefix`  

## Sơ đồ entity
Ví dụ cho thiết bị `gti283`:
- `sensor.gti283_power`, `sensor.gti283_energy_total`  
- `sensor.gti283_energy_daily`, `sensor.gti283_energy_monthly` (từ server)  
- `sensor.gti283_grid_voltage`, `sensor.gti283_grid_frequency`, `sensor.gti283_grid_energy_total`, `sensor.gti283_grid_energy_daily`, ...  
- `sensor.gti283_tieuthu_power`, `sensor.gti283_tieuthu_energy_total`, `sensor.gti283_tieuthu_energy_daily`, ...  
- `binary_sensor.gti283_online`  
- `number.gti283_cutoff_voltage`, `number.gti283_max_power_limit`  
- `input_datetime.gti283_schedule1_start`, `number.gti283_schedule1_cutoff_voltage`, ...

## Ghi chú
- Đây là Add-on dạng container, không phải custom_component.  
- Toàn bộ entity xuất hiện trong HA qua MQTT Discovery.  
- Daily & Monthly mặc định **lấy từ server**, không phải HA tự tính.  
- Bạn có thể tắt server và tự tính bằng utility_meter trong HA nếu muốn.

## Maintainer
Your Name <you@email.com>
