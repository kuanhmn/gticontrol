GTI_SENSORS = {
    "power":            ("Công suất hoà lưới", "W", "power", "measurement"),
    "energy_total":     ("Điện năng hoà lưới tổng", "kWh", "energy", "total_increasing"),
    "voltage_dc":       ("Điện áp DC", "V", "voltage", "measurement"),
    "current":          ("Dòng DC", "A", "current", "measurement"),
    "mosfet_temp":      ("Nhiệt độ Mosfet", "°C", "temperature", "measurement"),
    "cutoff_voltage":   ("Điện áp ngắt", "V", None, None),
    "max_power_limit":  ("Công suất giới hạn", "W", None, None)
}

GRID_SENSORS = {
    "grid_voltage":         ("Điện áp lưới", "V", "voltage", "measurement"),
    "grid_frequency":       ("Tần số lưới", "Hz", None, "measurement"),
    "grid_power":           ("Công suất lấy lưới", "W", "power", "measurement"),
    "grid_energy_total":    ("Điện năng lấy lưới tổng", "kWh", "energy", "total_increasing")
}

TIEUTHU_SENSORS = {
    "tieuthu_power":           ("Công suất tiêu thụ", "W", "power", "measurement"),
    "tieuthu_energy_total":    ("Điện năng tiêu thụ tổng", "kWh", "energy", "total_increasing")
}

DAILY_KEYS   = ["energy_daily","grid_energy_daily","tieuthu_energy_daily"]
MONTHLY_KEYS = ["energy_monthly","grid_energy_monthly","tieuthu_energy_monthly"]
