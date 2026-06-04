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
# 4. Plot monthly production vs target use
# --------------------------------------------------

months = range(1, 13)
plt.figure()
plt.bar(months, monthly_generated_kwh, label="Produced energy", alpha=0.7)
plt.plot(months, monthly_target_kwh, color="red", marker="o", linestyle="-", linewidth=2, label="Ammonia target")
plt.xlabel("Month")
plt.ylabel("Energy [kWh]")
plt.title("Monthly Solar Energy Produced vs Ammonia Energy Target")
plt.xticks(months)
plt.legend()
plt.grid(axis="y", linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()

# --------------------------------------------------
# 5. Plot PV output per square meter
# --------------------------------------------------

plt.figure()
plt.plot(hourly_energy_per_m2_kwh * required_field_area_m2)
plt.xlabel("Hour of the year")
plt.ylabel("PV output [kWh] per hour")
plt.title("Hourly PV output for required solar field")
plt.grid(True)
plt.show() 