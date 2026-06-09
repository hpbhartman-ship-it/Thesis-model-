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
start_idx = 0
for hours in hours_per_month:
    end_idx = start_idx + hours
    month_energy_m2 = hourly_energy_per_m2_kwh.iloc[start_idx:end_idx].sum()
    monthly_energy_per_m2_kwh.append(month_energy_m2)
    start_idx = end_idx

monthly_energy_per_m2_kwh = pd.Series(monthly_energy_per_m2_kwh, index=range(1, 13))

# --------------------------------------------------
# 4. Simulation with fixed design parameters
# --------------------------------------------------

# Fixed design parameters (supervisor-specified)
sim_field_area_m2   = 12_500   # m²
sim_storage_mwh     = 7.5      # MWh
sim_electrolyzer_mw = 0.5      # MW

sim_pv_mw = sim_field_area_m2 * max_irradiance * efficiency / 1e6

print(f"\n--- Simulation design parameters ---")
print(f"Solar field:  {sim_field_area_m2:,} m²  ({sim_pv_mw:.3f} MW peak)")
print(f"Battery:      {sim_storage_mwh} MWh")
print(f"Electrolyzer: {sim_electrolyzer_mw} MW")


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
        # HB draws 3/7 of electrolyzer power simultaneously; total plant limit = electrolyzer × 10/7
        battery_possible = min(current_storage * eta_discharge,
                               electrolyzer_limit_mw * (10.0 / 7.0) - solar_power_mw)
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
            # Need enough for electrolyzer minimum AND proportional HB draw
            if total_available_power >= minimum_production_limit_mw * (10.0 / 7.0):
                plant_state = "producing"
            elif total_available_power < equilibrium_threshold_mw:
                plant_state = "rampdown"
                rampdown_progress = 0.0

        elif plant_state == "producing":
            available_solar = solar_power_mw
            available_battery = current_storage * eta_discharge
            available_total = available_solar + available_battery
            # Check minimum: available for electrolyzer (7/10 of total) must meet its minimum
            if available_total * (7.0 / 10.0) >= minimum_production_limit_mw:
                # Electrolyzer power capped by its own limit and available power
                prod_power_elec = min(electrolyzer_limit_mw, available_total * (7.0 / 10.0))
                # HB runs proportionally; total plant draw = electrolyzer × 10/7
                prod_power_total = prod_power_elec * (10.0 / 7.0)
                battery_needed = max(0.0, prod_power_total - available_solar)
                battery_draw_actual = min(battery_needed / eta_discharge, current_storage)
                real_battery_power = battery_draw_actual * eta_discharge
                real_solar_power = min(prod_power_total, available_solar)
                real_total_power = real_solar_power + real_battery_power  # electrolyzer + HB
                ammonia_power_used[h] = real_total_power
                current_storage -= battery_draw_actual
                excess_solar = max(0.0, solar_power_mw - real_total_power)
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
    total_power_series = pd.Series(ammonia_power_used)
    return {
        "success": all(monthly_energy_used_kwh >= monthly_target_energy_kwh),
        "monthly_energy_used_kwh": monthly_energy_used_kwh,
        "storage_level": pd.Series(storage_level),
        "ammonia_power_used_mw": total_power_series,
        "electrolyzer_power_mw": total_power_series * (7.0 / 10.0),
        "hb_power_mw": total_power_series * (3.0 / 10.0),
        "plant_state_num": pd.Series(plant_state_num),
        "battery_loss_mwh": battery_loss_mwh,
        "battery_charged_total_mwh": battery_charged_total,
        "battery_discharged_total_mwh": battery_discharged_total,
    }

sim_result = simulate_ammonia_plant(sim_electrolyzer_mw, sim_storage_mwh, sim_field_area_m2)

# --------------------------------------------------
# Annual energy balance
# --------------------------------------------------

eta_charge    = 0.92
eta_discharge = 0.92

total_solar_mwh    = (hourly_energy_per_m2_kwh * sim_field_area_m2 / 1000).sum()
total_ammonia_mwh  = sim_result["monthly_energy_used_kwh"].sum() / 1000
bat_charged_mwh    = sim_result["battery_charged_total_mwh"]
bat_discharged_mwh = sim_result["battery_discharged_total_mwh"]
bat_losses_mwh     = sim_result["battery_loss_mwh"]
final_battery_mwh  = float(sim_result["storage_level"].iloc[-1])

# Solar splits into: direct to plant | into battery (input) | curtailed
solar_direct_mwh   = total_ammonia_mwh - bat_discharged_mwh * eta_discharge
solar_to_bat_mwh   = bat_charged_mwh / eta_charge
curtailed_mwh      = total_solar_mwh - solar_direct_mwh - solar_to_bat_mwh

# Electrolyzer / HB split (proportional by energy fraction)
total_elec_mwh = total_ammonia_mwh * (7.0 / 10.0)
total_hb_mwh   = total_ammonia_mwh * (3.0 / 10.0)

annual_target_mwh = monthly_ammonia_energy_kwh * 12 / 1000
months_met = int((sim_result["monthly_energy_used_kwh"] >= monthly_target_energy_kwh).sum())

print(f"\n--- Annual energy balance ---")
print(f"Total solar generated:              {total_solar_mwh:>8.1f} MWh  (100%)")
print(f"  → Direct to plant (solar):        {solar_direct_mwh:>8.1f} MWh  ({solar_direct_mwh/total_solar_mwh*100:.1f}%)")
print(f"  → Into battery (input):           {solar_to_bat_mwh:>8.1f} MWh  ({solar_to_bat_mwh/total_solar_mwh*100:.1f}%)")
print(f"  → Curtailed / wasted:             {curtailed_mwh:>8.1f} MWh  ({curtailed_mwh/total_solar_mwh*100:.1f}%)")
print(f"Battery → plant:                    {bat_discharged_mwh*eta_discharge:>8.1f} MWh")
print(f"Battery losses:                     {bat_losses_mwh:>8.1f} MWh")
print(f"Battery level at year-end:          {final_battery_mwh:>8.2f} MWh")
print(f"Total plant energy:                 {total_ammonia_mwh:>8.1f} MWh  (target: {annual_target_mwh:.1f} MWh)")
print(f"  → Electrolyzer (7 kWh/kg, {7/10*100:.0f}%): {total_elec_mwh:>8.1f} MWh")
print(f"  → Haber-Bosch  (3 kWh/kg, {3/10*100:.0f}%): {total_hb_mwh:>8.1f} MWh")
print(f"Monthly target met:                 {months_met}/12 months\n")

for month in range(1, 13):
    produced = sim_result["monthly_energy_used_kwh"][month]
    target   = monthly_ammonia_energy_kwh
    elec_kwh = produced * (7.0 / 10.0)
    hb_kwh   = produced * (3.0 / 10.0)
    status   = "OK" if produced >= target else f"short by {target - produced:,.0f} kWh"
    print(f"  Month {month:2d}: total {produced:>9,.0f} kWh "
          f"(elec {elec_kwh:,.0f} + HB {hb_kwh:,.0f}) / {target:,.0f} kWh  [{status}]")

# --------------------------------------------------
# Plant state statistics
# --------------------------------------------------

state_series = sim_result["plant_state_num"]
state_names  = {0: "Off", 1: "Ramp-up", 2: "Standby", 3: "Producing", 4: "Ramp-down"}
total_hours  = len(state_series)

print("\n--- Plant state statistics ---")
for code, name in state_names.items():
    hours = int((state_series == code).sum())
    pct   = hours / total_hours * 100
    print(f"  {name:<12}: {hours:>5} h  ({pct:.1f}%)")

# Monthly solar available for this field
monthly_solar_sim_kwh = monthly_energy_per_m2_kwh * sim_field_area_m2

# --------------------------------------------------
# Per-month battery charging / discharging from storage_level
# --------------------------------------------------

storage = sim_result["storage_level"]
monthly_bat_charged_kwh   = []
monthly_bat_discharged_kwh = []
start_idx = 0
for month_hours in hours_per_month:
    end_idx = start_idx + month_hours
    charged = 0.0
    discharged = 0.0
    for i in range(start_idx, end_idx):
        prev = float(storage.iloc[i - 1]) if i > 0 else 0.0
        delta = float(storage.iloc[i]) - prev
        if delta > 0:
            charged += delta
        else:
            discharged -= delta
    monthly_bat_charged_kwh.append(charged * 1000)
    monthly_bat_discharged_kwh.append(discharged * 1000)
    start_idx = end_idx

monthly_bat_charged_kwh    = pd.Series(monthly_bat_charged_kwh,    index=range(1, 13))
monthly_bat_discharged_kwh = pd.Series(monthly_bat_discharged_kwh, index=range(1, 13))

# Solar splits per month (all in kWh):
#   solar_available = solar_to_plant_direct + solar_to_battery + curtailed
solar_to_bat_kwh          = monthly_bat_charged_kwh / eta_charge   # raw solar consumed to charge battery
bat_contribution_kwh      = monthly_bat_discharged_kwh * eta_discharge  # battery energy delivered to plant
solar_to_plant_direct_kwh = (sim_result["monthly_energy_used_kwh"] - bat_contribution_kwh).clip(lower=0)
curtailed_monthly_kwh     = (monthly_solar_sim_kwh - solar_to_plant_direct_kwh - solar_to_bat_kwh).clip(lower=0)

# --------------------------------------------------
# 5. Monthly solar allocation: stacked breakdown
# --------------------------------------------------

months = range(1, 13)
bottom_bat = solar_to_plant_direct_kwh
bottom_curt = solar_to_plant_direct_kwh + solar_to_bat_kwh

plt.figure()
plt.bar(months, solar_to_plant_direct_kwh, label="Solar → plant (direct)",
        color="steelblue")
plt.bar(months, solar_to_bat_kwh, bottom=bottom_bat,
        label="Solar → battery (stored)", color="mediumseagreen")
plt.bar(months, curtailed_monthly_kwh, bottom=bottom_curt,
        label="Curtailed (wasted)", color="lightcoral")
plt.plot(months, sim_result["monthly_energy_used_kwh"], "s--",
         color="navy", linewidth=1.8, label="Total to plant (incl. battery)")
plt.plot(months, monthly_target_energy_kwh, "o-",
         color="red", linewidth=2, label="Ammonia target")
plt.xlabel("Month")
plt.ylabel("Energy [kWh]")
plt.title(f"Monthly solar allocation — {sim_field_area_m2:,} m², "
          f"{sim_electrolyzer_mw} MW electrolyzer, {sim_storage_mwh} MWh battery")
plt.xticks(months)
plt.legend(loc="upper right")
plt.grid(axis="y", linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 6. Annual energy breakdown (pie chart)
# --------------------------------------------------

pie_labels = ["Electrolyzer\n(direct solar)", "Electrolyzer\n(from battery)",
              "Battery losses", "Curtailed", "Left in battery"]
pie_values = [solar_direct_mwh, bat_discharged_mwh * eta_discharge,
              bat_losses_mwh, max(0.0, curtailed_mwh), final_battery_mwh]
pie_colors = ["steelblue", "cornflowerblue", "salmon", "lightgray", "mediumseagreen"]

plt.figure()
plt.pie(pie_values, labels=pie_labels, colors=pie_colors, autopct="%1.1f%%", startangle=90)
plt.title(f"Annual solar energy split — total {total_solar_mwh:.1f} MWh")
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 7. Battery storage level over the year
# --------------------------------------------------

plt.figure()
plt.fill_between(range(8760), sim_result["storage_level"], alpha=0.4, color="cornflowerblue", label="Storage level")
plt.plot(sim_result["storage_level"], linewidth=0.6, color="steelblue")
plt.axhline(sim_storage_mwh, color="red", linestyle="--", linewidth=1.5,
            label=f"Capacity ({sim_storage_mwh} MWh)")
plt.xlabel("Hour of the year")
plt.ylabel("Battery level [MWh]")
plt.title(f"Battery storage level — {sim_storage_mwh} MWh capacity")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 8. Hourly power split: electrolyzer vs Haber-Bosch
# --------------------------------------------------

hours = range(8760)
elec_mw = sim_result["electrolyzer_power_mw"]
hb_mw   = sim_result["hb_power_mw"]

plt.figure()
plt.fill_between(hours, elec_mw, alpha=0.7, color="steelblue", label=f"Electrolyzer (7 kWh/kg)")
plt.fill_between(hours, elec_mw, elec_mw + hb_mw, alpha=0.7, color="darkorange",
                 label=f"Haber-Bosch loop (3 kWh/kg)")
plt.axhline(sim_electrolyzer_mw, color="steelblue", linestyle="--", linewidth=1,
            label=f"Electrolyzer limit ({sim_electrolyzer_mw} MW)")
plt.axhline(sim_electrolyzer_mw * (10.0 / 7.0), color="red", linestyle="--", linewidth=1,
            label=f"Total plant limit ({sim_electrolyzer_mw * (10/7):.2f} MW)")
plt.xlabel("Hour of the year")
plt.ylabel("Power [MW]")
plt.title(f"Hourly power — electrolyzer ({sim_electrolyzer_mw} MW) + Haber-Bosch loop")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 9. Hourly PV output for the simulated field
# --------------------------------------------------

plt.figure()
plt.plot(hourly_energy_per_m2_kwh * sim_field_area_m2, linewidth=0.6, color="orange")
plt.xlabel("Hour of the year")
plt.ylabel("PV output [kWh] per hour")
plt.title(f"Hourly PV output — {sim_field_area_m2:,} m²  ({sim_pv_mw:.3f} MW peak)")
plt.grid(True)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 10. Plant state percentage bar chart
# --------------------------------------------------

state_codes   = [0, 1, 2, 3, 4]
state_labels  = ["Off", "Ramp-up", "Standby", "Producing", "Ramp-down"]
state_colors  = ["lightgray", "orange", "gold", "steelblue", "salmon"]
counts        = [(state_series == c).sum() for c in state_codes]
percentages   = [c / total_hours * 100 for c in counts]

plt.figure()
bars = plt.bar(state_labels, percentages, color=state_colors, edgecolor="black", linewidth=0.5)
for bar, pct, hrs in zip(bars, percentages, counts):
    plt.text(bar.get_x() + bar.get_width() / 2,
             bar.get_height() + 0.3,
             f"{pct:.1f}%\n({hrs} h)",
             ha="center", va="bottom", fontsize=9)
plt.ylabel("Time [%]")
plt.title("Plant state distribution — fraction of year")
plt.ylim(0, max(percentages) * 1.2)
plt.grid(axis="y", linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()