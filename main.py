import pandas as pd
import matplotlib.pyplot as plt

# --------------------------------------------------
# 1. Load weather data
# --------------------------------------------------

# Replace this with the name of your weather data file
file_path = "weather_data.csv"

# Load CSV file
weather = pd.read_csv(file_path)

# Show first rows to check if the file is loaded correctly
print(weather.head())

# Show all column names
print("Columns in file:")
print(weather.columns)

# --------------------------------------------------
# 2. Select solar data
# --------------------------------------------------

# Option A: if your file already has a capacity factor column
# Change 'capacity_factor' to the actual column name in your CSV
capacity_factor = weather["capacity_factor"]

# Calculate average capacity factor
average_cf = capacity_factor.mean()

print(f"Average capacity factor: {average_cf:.4f}")
print(f"Average capacity factor: {average_cf * 100:.2f}%")

# --------------------------------------------------
# 3. Calculate PV power output
# --------------------------------------------------

# Assumptions
pv_capacity_kw = 1000  # installed PV capacity in kW = 1 MW

# Hourly PV output in kW
pv_output_kw = capacity_factor * pv_capacity_kw

# Annual PV electricity production in kWh
annual_pv_energy_kwh = pv_output_kw.sum()

print(f"Annual PV electricity production: {annual_pv_energy_kwh:,.0f} kWh")

# --------------------------------------------------
# 4. Plot PV output
# --------------------------------------------------

plt.figure()
plt.plot(pv_output_kw)
plt.xlabel("Hour of the year")
plt.ylabel("PV output [kW]")
plt.title("Hourly PV output")
plt.grid(True)
plt.show()

# testen hoe dit nu gaat
# nog een keer testen 