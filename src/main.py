import matplotlib
matplotlib.use('TkAgg') # Crucial fix for animation crashes

import datetime as dt
import math
import requests
import customtkinter as ctk
from tkinter import messagebox
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation

# --- CONFIGURATION ---
API_KEY = "44ea711e2eb03eb4bf384faf7dea0676"
BASE_URL = "https://api.openweathermap.org/data/2.5/weather?"
PANEL_WIDTH = 1.0
PANEL_HEIGHT = 1.6
PANEL_WEIGHT = 20

# --- BACKEND LOGIC ---
def fetch_weather_data(city_name):
    try:
        url = f"{BASE_URL}appid={API_KEY}&q={city_name}"
        response = requests.get(url).json()
        if response.get('cod') != 200:
            return None, response.get('message', 'Unknown error')
        return response, None
    except Exception as e:
        return None, str(e)

def calculate_solar_position(latitude, longitude, date_time, timezone_offset):
    date_time_utc = date_time - dt.timedelta(seconds=timezone_offset)
    day_of_year = date_time_utc.timetuple().tm_yday
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1 + (date_time_utc.hour - 12) / 24.0)
    
    declination = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) -
                   0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma) -
                   0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    
    time_offset = (229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma) -
                             0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma)))
    
    true_solar_time = (date_time_utc.hour * 60 + date_time_utc.minute + date_time_utc.second / 60 +
                        time_offset + 4 * longitude)
    
    hour_angle = math.radians((true_solar_time / 4) - 180)
    latitude_rad = math.radians(latitude)
    solar_zenith_angle = math.acos(math.sin(latitude_rad) * math.sin(declination) +
                                    math.cos(latitude_rad) * math.cos(declination) * math.cos(hour_angle))
    
    solar_elevation_angle = math.pi / 2 - solar_zenith_angle
    solar_azimuth_angle = math.atan2(math.sin(hour_angle),
                                     (math.cos(hour_angle) * math.sin(latitude_rad) - math.tan(declination) * math.cos(latitude_rad)))  
    solar_azimuth_angle = (solar_azimuth_angle + 2 * math.pi) % (2 * math.pi) 

    return math.degrees(solar_elevation_angle), math.degrees(solar_azimuth_angle)

def calculate_motor_torque(wind_speed, elevation_angle):
    g = 9.81
    wind_pressure = 0.613 * wind_speed ** 2
    weight_torque = (PANEL_WEIGHT * g) * (PANEL_HEIGHT / 2) * math.cos(math.radians(elevation_angle))
    wind_torque = (wind_pressure * (PANEL_WIDTH * PANEL_HEIGHT)) * (PANEL_HEIGHT / 2) * math.sin(math.radians(elevation_angle))
    return weight_torque + wind_torque

def calculate_efficiency(cloudiness_pct, is_night):
    if is_night: return 0.0
    eff = 100 - (cloudiness_pct * 0.8)
    return max(0, eff)

def format_time(timestamp, tz_offset):
    tz = dt.timezone(dt.timedelta(seconds=tz_offset))
    local_dt = dt.datetime.fromtimestamp(timestamp, tz)
    return local_dt.strftime("%H:%M")

# --- GUI CLASS ---

class SolarApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.geometry("1100x750") 
        self.title("Solar Panel Control System")
        ctk.set_appearance_mode("Dark")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- LEFT PANEL ---
        self.left_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        
        self.header = ctk.CTkLabel(self.left_frame, text="Control Panel", font=("Roboto", 20, "bold"))
        self.header.pack(pady=20)

        # Inputs
        self.city_entry = ctk.CTkEntry(self.left_frame, placeholder_text="City Name")
        self.city_entry.pack(pady=10, padx=20)
        
        self.search_btn = ctk.CTkButton(self.left_frame, text="Get Data & Calculate", command=self.update_data)
        self.search_btn.pack(pady=10)

        self.stop_sim_btn = ctk.CTkButton(self.left_frame, fg_color="#C0392B", text="Stop Simulation", state="disabled", command=self.stop_the_simulation)
        self.stop_sim_btn.pack(pady=10)

        # Data Display
        self.stats_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.stats_frame.pack(pady=20, padx=10, fill="x")
        
        self.lbl_status = ctk.CTkLabel(self.stats_frame, text="STATUS: WAITING", font=("Roboto", 14, "bold"), text_color="gray")
        self.lbl_status.pack(pady=(0, 15))

        self.lbl_time = self.add_stat_label("Current Time:")
        self.lbl_desc = self.add_stat_label("Condition:")
        self.lbl_temp = self.add_stat_label("Temperature:")
        self.lbl_wind = self.add_stat_label("Wind Speed:")
        self.lbl_clouds = self.add_stat_label("Cloudiness:")
        self.lbl_eff = self.add_stat_label("Est. Efficiency:")
        self.lbl_elev = self.add_stat_label("Solar Elev:")
        self.lbl_azi = self.add_stat_label("Solar Azi:")
        self.lbl_torque = self.add_stat_label("Torque:")

        self.start_sim_btn = ctk.CTkButton(self.left_frame, text="Start View Animation", 
                                            fg_color="#27AE60", state="disabled", command=self.embed_animation)
        self.start_sim_btn.pack(pady=20, side="bottom")

        # --- RIGHT PANEL ---
        self.right_frame = ctk.CTkFrame(self, fg_color="#1e1e1e")
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.plot_label = ctk.CTkLabel(self.right_frame, text="Dual-Axis Tracking Visualization", font=("Roboto", 16))
        self.plot_label.pack(pady=10)
        
        self.canvas_frame = ctk.CTkFrame(self.right_frame)
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Variables
        self.ani = None 
        self.canvas = None
        self.sim_data = {} 
        self.is_running = False

    def add_stat_label(self, text):
        container = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        container.pack(fill="x", pady=5)
        ctk.CTkLabel(container, text=text, anchor="w").pack(side="left")
        val_lbl = ctk.CTkLabel(container, text="--", font=("Roboto", 12, "bold"), text_color="#3B8ED0")
        val_lbl.pack(side="right")
        return val_lbl

    def update_data(self):
        city = self.city_entry.get()
        if not city: return

        response, error = fetch_weather_data(city)
        if error:
            messagebox.showerror("Error", str(error))
            return

        # Parsing
        desc = response['weather'][0]['description'].title()
        temp_c = response['main']['temp'] - 273.15
        wind = response['wind']['speed']
        clouds = response['clouds']['all']
        lat = response['coord']['lat']
        lon = response['coord']['lon']
        tz_offset = response['timezone']
        
        # Time & Logic
        tz = dt.timezone(dt.timedelta(seconds=tz_offset))
        current_dt = dt.datetime.now(tz)
        current_ts = current_dt.timestamp()
        
        sunrise_ts = response['sys']['sunrise']
        sunset_ts = response['sys']['sunset']
        
        sunrise_str = format_time(sunrise_ts, tz_offset)
        sunset_str = format_time(sunset_ts, tz_offset)
        current_time_str = current_dt.strftime("%H:%M")

        is_night = (current_ts < sunrise_ts) or (current_ts > sunset_ts)

        elev, azi = calculate_solar_position(lat, lon, current_dt, tz_offset)
        
        if is_night:
            elev = 0 
            azi = 0 
            torque = 0
            efficiency = 0
            self.lbl_status.configure(text="STATUS: OFFLINE (Night)", text_color="#E74C3C")
        else:
            torque = calculate_motor_torque(wind, elev)
            efficiency = calculate_efficiency(clouds, is_night)
            self.lbl_status.configure(text="STATUS: ONLINE (Tracking)", text_color="#2ECC71")

        self.lbl_time.configure(text=current_time_str)
        self.lbl_desc.configure(text=desc)
        self.lbl_temp.configure(text=f"{temp_c:.1f} °C")
        self.lbl_wind.configure(text=f"{wind} m/s")
        self.lbl_clouds.configure(text=f"{clouds} %")
        self.lbl_eff.configure(text=f"{efficiency:.1f} %")
        self.lbl_elev.configure(text=f"{elev:.2f}°")
        self.lbl_azi.configure(text=f"{azi:.2f}°")
        self.lbl_torque.configure(text=f"{torque:.2f} Nm")
        
        self.sim_data = {
            "elev": elev,
            "azi": azi,
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "is_night": is_night
        }
        
        self.start_sim_btn.configure(state="normal")
    
    def stop_the_simulation(self):
        self.is_running = False
        if self.ani and self.ani.event_source:
            self.ani.event_source.stop()
            self.ani = None
        if self.canvas:
            try: self.canvas.get_tk_widget().destroy()
            except: pass
            self.canvas = None
        self.stop_sim_btn.configure(state="disabled") 
        self.start_sim_btn.configure(state="normal")
    
    def on_closing(self):
        self.is_running = False
        if self.ani and self.ani.event_source:
            self.ani.event_source.stop()
        self.quit()
        self.destroy()

    def embed_animation(self):
        self.start_sim_btn.configure(state="disabled")
        self.stop_sim_btn.configure(state="normal")
        self.is_running = True

        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            if self.ani and self.ani.event_source: 
                self.ani.event_source.stop()
        
        fig, (ax_elev, ax_azi) = plt.subplots(1, 2, figsize=(8, 4), dpi=100)
        fig.patch.set_facecolor('#2b2b2b')

        # Variables
        target_elev = self.sim_data.get("elev", 0)
        target_azi = self.sim_data.get("azi", 0)
        rise_txt = self.sim_data.get("sunrise", "06:00")
        set_txt = self.sim_data.get("sunset", "18:00")
        is_night = self.sim_data.get("is_night", False)

        # --- LEFT PLOT: ELEVATION ---
        ax_elev.set_facecolor('#2b2b2b')
        ax_elev.set_title("Elevation (Side View)", color="white", fontsize=10)
        ax_elev.set_xlim(-0.5, 1.5) # Shifted right to make room for text
        ax_elev.set_ylim(-0.1, 1.2)
        ax_elev.set_aspect('equal')
        ax_elev.axis('off')
        
        # Ground Line
        ax_elev.plot([-0.5, 1.2], [0, 0], color='gray', linewidth=2)
        
        # INFO BOX (Right Side)
        ax_elev.text(0.8, 1.0, "SOLAR SCHEDULE", color="#3498DB", fontsize=8, fontweight='bold')
        ax_elev.text(0.8, 0.85, f"Sunrise: {rise_txt}", color="#F39C12", fontsize=9)
        ax_elev.text(0.8, 0.70, f"Sunset:  {set_txt}", color="#E67E22", fontsize=9)

        # Dynamic Elements
        sun_elev, = ax_elev.plot([], [], 'o', color='#F1C40F', markersize=12) 
        panel_elev_line, = ax_elev.plot([], [], color='#3498DB', linewidth=5) 
        arrow_elev = ax_elev.quiver(0, 0, 0, 0, scale=1, scale_units='xy', color='#E74C3C', width=0.015)
        angle_arc = patches.Arc((0, 0), 0.4, 0.4, angle=0, theta1=0, theta2=0, color='white', linestyle='--')
        ax_elev.add_patch(angle_arc)
        elev_text = ax_elev.text(0.1, 0.1, "", color="white", fontsize=9, fontweight="bold")
        offline_text_1 = ax_elev.text(0, 0.6, "OFFLINE", color="#C0392B", fontsize=16, fontweight="bold", ha="center", alpha=0)

        # --- RIGHT PLOT: AZIMUTH ---
        ax_azi.set_facecolor('#2b2b2b')
        ax_azi.set_title("Compass Orientation (Top-Down)", color="white", fontsize=10)
        ax_azi.set_xlim(-1.2, 1.2)
        ax_azi.set_ylim(-1.2, 1.2)
        ax_azi.set_aspect('equal')
        ax_azi.axis('off')

        compass_circle = plt.Circle((0, 0), 0.9, color='#555555', fill=False, linestyle=':')
        ax_azi.add_patch(compass_circle)
        ax_azi.text(0, 1.0, "N", color='white', ha='center', fontweight='bold', fontsize=8)
        ax_azi.text(1.0, 0, "E", color='white', va='center', fontweight='bold', fontsize=8)
        ax_azi.text(0, -1.0, "S", color='white', ha='center', fontweight='bold', fontsize=8)
        ax_azi.text(-1.0, 0, "W", color='white', va='center', fontweight='bold', fontsize=8)

        sun_azi, = ax_azi.plot([], [], 'o', color='#F1C40F', markersize=12)
        panel_rect = plt.Polygon([[0,0]], closed=True, color='#3498DB', alpha=0.8)
        ax_azi.add_patch(panel_rect)
        arrow_azi = ax_azi.quiver(0, 0, 0, 0, scale=1, scale_units='xy', color='#E74C3C', width=0.015, zorder=10)
        azi_text = ax_azi.text(0, 0, "", color="white", ha="center", va="center", fontsize=9, fontweight="bold", zorder=11)
        offline_text_2 = ax_azi.text(0, 0, "NIGHT MODE", color="#C0392B", fontsize=12, fontweight="bold", ha="center", alpha=0)

        # --- ANIMATION LOGIC ---
        frames = 60
        if target_elev < 0: target_elev = 0 

        def update(frame):
            if not self.is_running or not plt.fignum_exists(fig.number): return sun_elev,

            try:
                # Night Mode logic
                if is_night:
                    offline_text_1.set_alpha(1)
                    offline_text_2.set_alpha(1)
                    sun_elev.set_data([], [])
                    panel_elev_line.set_data([-0.2, 0.2], [0, 0]) 
                    arrow_elev.set_UVC(0, 0)
                    sun_azi.set_data([], [])
                    arrow_azi.set_UVC(0, 0)
                    w, h = 0.1, 0.25
                    panel_rect.set_xy([(-w, -h), (w, -h), (w, h), (-w, h)])
                    return sun_elev, panel_elev_line, arrow_elev, offline_text_1, offline_text_2

                progress = frame / frames
                curr_elev = target_elev * progress
                rad_elev = math.radians(curr_elev)
                curr_azi = target_azi * progress
                rad_azi = math.radians(curr_azi)

                # --- PLOT 1: ELEVATION (UP/DOWN) ---
                # Sun Logic: Simple circular arc (x=cos, y=sin)
                ex = math.cos(rad_elev)
                ey = math.sin(rad_elev)
                sun_elev.set_data([ex], [ey])
                
                # Panel Logic
                px = 0.2 * math.cos(rad_elev + math.pi/2)
                py = 0.2 * math.sin(rad_elev + math.pi/2)
                panel_elev_line.set_data([-px, px], [-py, py])
                
                arrow_elev.set_UVC(ex*0.8, ey*0.8)
                angle_arc.theta2 = curr_elev
                elev_text.set_text(f"{curr_elev:.1f}°")

                # --- PLOT 2: AZIMUTH (COMPASS) ---
                ax_sun = math.sin(rad_azi)
                ay_sun = math.cos(rad_azi)
                sun_azi.set_data([ax_sun], [ay_sun])
                arrow_azi.set_UVC(ax_sun*0.8, ay_sun*0.8)

                w, h = 0.1, 0.25 
                panel_angle = -rad_azi - (math.pi / 2) 
                cos_a = math.cos(panel_angle) 
                sin_a = math.sin(panel_angle)
                corners = [(-w, -h), (w, -h), (w, h), (-w, h)] 
                rotated_corners = []
                for x, y in corners:
                    rx = x * cos_a - y * sin_a
                    ry = x * sin_a + y * cos_a
                    rotated_corners.append([rx, ry])
                panel_rect.set_xy(rotated_corners)
                azi_text.set_text(f"{curr_azi:.1f}°")

                return sun_elev, panel_elev_line, arrow_elev, elev_text, sun_azi, panel_rect, arrow_azi, azi_text

            except Exception:
                return sun_elev,

        self.canvas = FigureCanvasTkAgg(fig, master=self.canvas_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.ani = FuncAnimation(fig, update, frames=frames+1, interval=30, repeat=False)

if __name__ == "__main__":
    app = SolarApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.destroy()
    except Exception as e:
        print(f"Application closed with error: {e}")