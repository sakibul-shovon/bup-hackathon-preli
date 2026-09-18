def format_hours(hours: list[int]) -> str:
    if not hours:
        return ""
    sorted_hours = sorted(set(hours))
    ranges = []
    start = sorted_hours[0]
    prev = sorted_hours[0]
    
    for h in sorted_hours[1:]:
        if h == prev + 1:
            prev = h
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = h
            prev = h
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")
    return ", ".join(ranges)

def build_summary(
    total_grid_kwh: float,
    total_cost_bdt: float,
    peak_grid_kwh: float,
    peak_hour: int,
    charge_hours: list[int],
    discharge_hours: list[int],
    applied_types: list[str],
) -> str:
    s = f"Purchased {total_grid_kwh} kWh from the grid for {total_cost_bdt} BDT, peaking at {peak_grid_kwh} kWh in hour {peak_hour}. "
    
    battery_parts = []
    if charge_hours:
        battery_parts.append(f"charged the battery in hours {format_hours(charge_hours)}")
    if discharge_hours:
        battery_parts.append(f"discharged in hours {format_hours(discharge_hours)}")
    
    if battery_parts:
        clause = " and ".join(battery_parts)
        clause = clause[0].upper() + clause[1:]
        s += clause + ". "
            
    if applied_types:
        s += f"Applied operator directives: {', '.join(applied_types)}."
    else:
        s += "No operator directives affected this schedule."
        
    return s[:400]
