import pandas as pd
import matplotlib.pyplot as plt

# --------------------------------------------------
# 1. Load weather data
# --------------------------------------------------

# Load Excel file with solar capacity factors
file_path = "Renewables zon Gladstone.xlsx"

# Load Excel file - column H contains capacity factors
weather = pd.read_excel(file_path)

# Show first rows to check if the file is loaded correctly
#print(weather.head())

# Show all column names
#print("Columns in file:")
#print(weather.columns)

# --------------------------------------------------
# 2. Select solar data
# --------------------------------------------------

# Column H contains the capacity factors
capacity_factor = weather.iloc[:, 7]  # Column H is the 8th column (0-indexed: 7)

# Calculate average capacity factor
average_cf = capacity_factor.mean()

#print(f"Average capacity factor: {average_cf:.4f}")
#print(f"Average capacity factor: {average_cf * 100:.2f}%")

# --------------------------------------------------
# 3. Ammonia target and solar field sizing
# --------------------------------------------------

# Ammonia production target and energy requirement
ammonia_target_ton_per_month = 25  # ton/month
energy_needed_per_kg_kwh = 10  # kWh/kg
monthly_ammonia_energy_kwh = ammonia_target_ton_per_month * 1000 * energy_needed_per_kg_kwh
monthly_ammonia_energy_mwh = monthly_ammonia_energy_kwh / 1000

print(f"Monthly ammonia energy target: {monthly_ammonia_energy_mwh:.1f} MWh ({monthly_ammonia_energy_kwh:,.0f} kWh)")

# Solar PV assumptions
max_irradiance = 1000  # W/m^2
efficiency = 0.18  # [-]

# Hourly energy produced per square meter [kWh/m^2]
hourly_energy_per_m2_kwh = capacity_factor * max_irradiance * efficiency / 1000

# Monthly hour counts for a standard year
hours_per_month = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]

if len(hourly_energy_per_m2_kwh) != sum(hours_per_month):
    raise ValueError(
        f"Expected {sum(hours_per_month)} hourly rows, but got {len(hourly_energy_per_m2_kwh)}."
    )

monthly_energy_per_m2_kwh = []
monthly_area_required_m2 = []
start_idx = 0
for hours in hours_per_month:
    end_idx = start_idx + hours
    month_energy_m2 = hourly_energy_per_m2_kwh.iloc[start_idx:end_idx].sum()
    monthly_energy_per_m2_kwh.append(month_energy_m2)
    monthly_area_required_m2.append(monthly_ammonia_energy_kwh / month_energy_m2)
    start_idx = end_idx

monthly_energy_per_m2_kwh = pd.Series(monthly_energy_per_m2_kwh, index=range(1, 13))
monthly_area_required_m2 = pd.Series(monthly_area_required_m2, index=range(1, 13))

required_field_area_m2 = monthly_area_required_m2.max()
installed_power_capacity_mw = required_field_area_m2 * max_irradiance * efficiency / 1e6

print(f"Required field area to meet every monthly target: {required_field_area_m2:,.0f} m^2")
print(f"Installed power capacity at {efficiency*100:.0f}% efficiency: {installed_power_capacity_mw:.2f} MW")

# Monthly energy generation for the required field area
monthly_generated_kwh = monthly_energy_per_m2_kwh * required_field_area_m2
monthly_target_kwh = pd.Series([monthly_ammonia_energy_kwh] * 12, index=range(1, 13))
for month in range(1, 13):
    print(
        f"Month {month:2d}: generated {monthly_generated_kwh[month]:,.0f} kWh, "
        f"target {monthly_ammonia_energy_kwh:,.0f} kWh"
    )

# --------------------------------------------------
# 4. Battery / electrolyzer sizing
# --------------------------------------------------

energy_h2_per_kg_ammonia_kwh = 7
energy_synthesis_per_kg_ammonia_kwh = 3
monthly_h2_energy_kwh = ammonia_target_ton_per_month * 1000 * energy_h2_per_kg_ammonia_kwh
monthly_synthesis_energy_kwh = ammonia_target_ton_per_month * 1000 * energy_synthesis_per_kg_ammonia_kwh
print(f"Monthly H2 energy demand: {monthly_h2_energy_kwh:,.0f} kWh")
print(f"Monthly synthesis energy demand: {monthly_synthesis_energy_kwh:,.0f} kWh")

hourly_power_mw = hourly_energy_per_m2_kwh * required_field_area_m2 / 1000
monthly_target_energy_kwh = pd.Series([monthly_ammonia_energy_kwh] * 12, index=range(1, 13))

hours_per_month = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]


def simulate_ammonia_plant(electrolyzer_limit_mw, storage_capacity_mwh, field_area_m2):
    hourly_power_mw_local = hourly_energy_per_m2_kwh * field_area_m2 / 1000
    n_hours = len(hourly_power_mw_local)
    storage_level = [0.0] * n_hours
    ammonia_power_used = [0.0] * n_hours
    ammonia_energy_used_kwh = [0.0] * n_hours
    plant_state_num = [0] * n_hours

    eta_charge = 0.92
    eta_discharge = 0.92
    minimum_production_limit_mw = electrolyzer_limit_mw * 0.15
    equilibrium_threshold_mw = electrolyzer_limit_mw * 0.07
    ramp_time_hours = 4
    ramp_energy_mwh = equilibrium_threshold_mw * ramp_time_hours
    rampdown_time_hours = 3
    rampdown_energy_mwh = equilibrium_threshold_mw * rampdown_time_hours

    current_storage = 0.0
    ramp_progress = 0.0
    rampdown_progress = 0.0
    plant_state = "off"
    battery_charged_total = 0.0
    battery_discharged_total = 0.0

    for h in range(n_hours):
        solar_power_mw = float(hourly_power_mw_local.iloc[h])
        battery_possible = min(current_storage * eta_discharge, electrolyzer_limit_mw - solar_power_mw)
        battery_possible = max(0.0, battery_possible)
        total_available_power = solar_power_mw + battery_possible

        if plant_state == "off":
            ammonia_power_used[h] = 0.0
            if total_available_power >= equilibrium_threshold_mw:
                plant_state = "rampup"
                ramp_progress = 0.0
            else:
                current_storage = min(current_storage + solar_power_mw * eta_charge, storage_capacity_mwh)

        elif plant_state == "rampup":
            ammonia_power_used[h] = 0.0
            shortfall = max(0.0, equilibrium_threshold_mw - solar_power_mw)
            draw = min(shortfall / eta_discharge, current_storage)
            current_storage -= draw
            ramp_draw = min(total_available_power, equilibrium_threshold_mw)
            ramp_progress += ramp_draw
            excess = max(0.0, solar_power_mw - ramp_draw)
            current_storage = min(current_storage + excess * eta_charge, storage_capacity_mwh)
            if ramp_progress >= ramp_energy_mwh:
                plant_state = "standby"
                ramp_progress = 0.0
            elif total_available_power < equilibrium_threshold_mw:
                plant_state = "rampdown"
                rampdown_progress = rampdown_energy_mwh - ramp_progress

        elif plant_state == "standby":
            ammonia_power_used[h] = 0.0
            shortfall = max(0.0, equilibrium_threshold_mw - solar_power_mw)
            draw = min(shortfall / eta_discharge, current_storage)
            current_storage -= draw
            excess = max(0.0, solar_power_mw - equilibrium_threshold_mw)
            current_storage = min(current_storage + excess * eta_charge, storage_capacity_mwh)
            if total_available_power >= minimum_production_limit_mw:
                plant_state = "producing"
            elif total_available_power < equilibrium_threshold_mw:
                plant_state = "rampdown"
                rampdown_progress = 0.0

        elif plant_state == "producing":
            available_solar = solar_power_mw
            available_battery = current_storage * eta_discharge
            available_total = available_solar + available_battery
            if available_total >= minimum_production_limit_mw:
                prod_power = min(electrolyzer_limit_mw, available_total)
                battery_needed = max(0.0, prod_power - available_solar)
                battery_draw_actual = min(battery_needed / eta_discharge, current_storage)
                real_battery_power = battery_draw_actual * eta_discharge
                real_solar_power = min(prod_power, available_solar)
                real_total_power = real_solar_power + real_battery_power
                ammonia_power_used[h] = real_total_power
                current_storage -= battery_draw_actual
                excess_solar = max(0.0, solar_power_mw - ammonia_power_used[h])
                current_storage = min(current_storage + excess_solar * eta_charge, storage_capacity_mwh)
            else:
                plant_state = "standby"
                ammonia_power_used[h] = 0.0
                current_storage = min(current_storage + solar_power_mw * eta_charge, storage_capacity_mwh)

        elif plant_state == "rampdown":
            ammonia_power_used[h] = 0.0
            shortfall = max(0.0, equilibrium_threshold_mw - solar_power_mw)
            draw = min(shortfall / eta_discharge, current_storage)
            current_storage -= draw
            rampdown_progress += equilibrium_threshold_mw
            excess = max(0.0, solar_power_mw - equilibrium_threshold_mw)
            current_storage = min(current_storage + excess * eta_charge, storage_capacity_mwh)
            if rampdown_progress >= rampdown_energy_mwh:
                plant_state = "off"
                rampdown_progress = 0.0
            elif total_available_power >= equilibrium_threshold_mw:
                plant_state = "rampup"
                ramp_progress = ramp_energy_mwh - rampdown_progress

        current_storage = min(storage_capacity_mwh, max(0.0, current_storage))
        storage_level[h] = current_storage
        ammonia_energy_used_kwh[h] = ammonia_power_used[h] * 1000.0

        if h == 0:
            delta_storage = storage_level[h]
        else:
            delta_storage = storage_level[h] - storage_level[h - 1]
        if delta_storage > 0:
            battery_charged_total += delta_storage
        elif delta_storage < 0:
            battery_discharged_total -= delta_storage

        plant_state_num[h] = {
            "off": 0,
            "rampup": 1,
            "standby": 2,
            "producing": 3,
            "rampdown": 4,
        }[plant_state]

    monthly_energy_used_kwh = []
    start_idx = 0
    for hours in hours_per_month:
        end_idx = start_idx + hours
        monthly_energy_used_kwh.append(sum(ammonia_energy_used_kwh[start_idx:end_idx]))
        start_idx = end_idx
    monthly_energy_used_kwh = pd.Series(monthly_energy_used_kwh, index=range(1, 13))

    battery_loss_mwh = battery_charged_total * (1 - eta_charge) + battery_discharged_total * (1 - eta_discharge)
    return {
        "success": all(monthly_energy_used_kwh >= monthly_target_energy_kwh),
        "monthly_energy_used_kwh": monthly_energy_used_kwh,
        "storage_level": pd.Series(storage_level),
        "ammonia_power_used_mw": pd.Series(ammonia_power_used),
        "battery_loss_mwh": battery_loss_mwh,
        "battery_charged_total_mwh": battery_charged_total,
        "battery_discharged_total_mwh": battery_discharged_total,
    }

# Cost weights — adjust these to reflect relative capital costs
cost_weight_pv_per_mw = 1.0
cost_weight_elec_per_mw = 1.0
cost_weight_bat_per_mwh = 0.1

# Field area candidates: fractions of the worst-month-sized area
candidate_field_areas_m2 = [required_field_area_m2 * f for f in [0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]]
# Electrolyzer candidates: 0.5 to 5.0 MW in 0.5 MW steps
candidate_limits_mw = [i * 0.5 for i in range(1, 11)]

best_solution = None
best_partial = None

for field_area in candidate_field_areas_m2:
    pv_mw = field_area * max_irradiance * efficiency / 1e6
    for limit_mw in candidate_limits_mw:
        print(f"  PV {pv_mw:.2f} MW, electrolyzer {limit_mw:.1f} MW ...", end=" ", flush=True)
        feasible_storage = None
        for storage_mwh in range(0, 101):
            result = simulate_ammonia_plant(limit_mw, float(storage_mwh), field_area)
            if result["success"]:
                feasible_storage = storage_mwh
                break
            months_ok = int((result["monthly_energy_used_kwh"] >= monthly_target_energy_kwh).sum())
            if best_partial is None or months_ok > best_partial["months_ok"]:
                best_partial = {
                    "field_area_m2": field_area, "limit_mw": limit_mw,
                    "storage_mwh": storage_mwh, "months_ok": months_ok, "result": result,
                }
        if feasible_storage is not None:
            cost = (cost_weight_pv_per_mw * pv_mw
                    + cost_weight_elec_per_mw * limit_mw
                    + cost_weight_bat_per_mwh * feasible_storage)
            print(f"feasible at {feasible_storage} MWh battery (cost={cost:.2f})")
            if best_solution is None or cost < best_solution["cost"]:
                best_solution = {
                    "field_area_m2": field_area, "limit_mw": limit_mw,
                    "storage_mwh": feasible_storage, "cost": cost, "result": result,
                }
        else:
            print("no feasible storage found")

if best_solution is None:
    print("\nNo fully feasible solution found. Best partial result:")
    bp = best_partial
    bp_pv_mw = bp["field_area_m2"] * max_irradiance * efficiency / 1e6
    print(f"  PV: {bp_pv_mw:.2f} MW ({bp['field_area_m2']:,.0f} m²), "
          f"Electrolyzer: {bp['limit_mw']:.1f} MW, Battery: {bp['storage_mwh']} MWh")
    print(f"  Months meeting target: {bp['months_ok']}/12")
    for month in range(1, 13):
        produced = bp["result"]["monthly_energy_used_kwh"][month]
        shortfall = monthly_target_energy_kwh[month] - produced
        status = "OK" if shortfall <= 0 else f"SHORT by {shortfall:,.0f} kWh"
        print(f"  Month {month:2d}: {produced:,.0f} kWh  [{status}]")
    raise RuntimeError("No feasible solution found. Widen the search grid.")

opt_field_area_m2 = best_solution["field_area_m2"]
opt_pv_mw = opt_field_area_m2 * max_irradiance * efficiency / 1e6
opt_limit_mw = best_solution["limit_mw"]
opt_storage_mwh = best_solution["storage_mwh"]
opt_result = best_solution["result"]

print(f"\nOptimal solar field area: {opt_field_area_m2:,.0f} m²  ({opt_pv_mw:.2f} MW installed)")
print(f"Optimal electrolyzer limit: {opt_limit_mw:.2f} MW")
print(f"Optimal battery capacity: {opt_storage_mwh:.0f} MWh")
print(f"Total battery losses: {opt_result['battery_loss_mwh']:.2f} MWh")

for month in range(1, 13):
    produced = opt_result["monthly_energy_used_kwh"][month]
    target = monthly_ammonia_energy_kwh
    print(f"Month {month:2d}: produced {produced:,.0f} kWh, target {target:,.0f} kWh")

# --------------------------------------------------
# 5. Plot monthly production vs target use
# --------------------------------------------------

months = range(1, 13)
plt.figure()
plt.bar(months, opt_result["monthly_energy_used_kwh"], label="Produced energy", alpha=0.7)
plt.plot(months, monthly_target_kwh, color="red", marker="o", linestyle="-", linewidth=2, label="Ammonia target")
plt.xlabel("Month")
plt.ylabel("Energy [kWh]")
plt.title("Monthly Solar Energy Used for Ammonia vs Target")
plt.xticks(months)
plt.legend()
plt.grid(axis="y", linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 6. Plot hourly PV output for optimal solar field
# --------------------------------------------------

plt.figure()
plt.plot(hourly_energy_per_m2_kwh * opt_field_area_m2)
plt.xlabel("Hour of the year")
plt.ylabel("PV output [kWh] per hour")
plt.title(f"Hourly PV output — optimal field ({opt_field_area_m2:,.0f} m², {opt_pv_mw:.2f} MW)")
plt.grid(True)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 7. Plot battery storage level over the year
# --------------------------------------------------

plt.figure()
plt.fill_between(range(8760), opt_result["storage_level"], alpha=0.4, label="Storage level")
plt.plot(opt_result["storage_level"], linewidth=0.6)
plt.axhline(opt_storage_mwh, color="red", linestyle="--", linewidth=1.5, label=f"Capacity ({opt_storage_mwh:.0f} MWh)")
plt.xlabel("Hour of the year")
plt.ylabel("Battery level [MWh]")
plt.title(f"Battery storage level — {opt_storage_mwh:.0f} MWh capacity")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 8. Plot hourly electrolyzer production
# --------------------------------------------------

plt.figure()
plt.fill_between(range(8760), opt_result["ammonia_power_used_mw"], alpha=0.4, label="Electrolyzer output")
plt.plot(opt_result["ammonia_power_used_mw"], linewidth=0.6)
plt.axhline(opt_limit_mw, color="red", linestyle="--", linewidth=1.5, label=f"Limit ({opt_limit_mw:.1f} MW)")
plt.xlabel("Hour of the year")
plt.ylabel("Power to electrolyzer [MW]")
plt.title(f"Hourly electrolyzer production — {opt_limit_mw:.1f} MW limit")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show() 