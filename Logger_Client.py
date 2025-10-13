"""
ESP32 BLE Multi-Device Flow Scanner Dashboard
Requires: bleak, matplotlib
Usage: python ble_flow_dashboard.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
from datetime import datetime, timedelta
from collections import deque
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
from bleak import BleakScanner, BleakClient
import csv
import os

print("Starting application...")

class FlowDevice:
    """Single BLE flow device instance"""
    def __init__(self, device_id, device_name, address):
        self.device_id = device_id
        self.device_name = device_name
        self.address = address
        self.client = None
        self.connected = False
        self.monitoring = False
        
        # Data storage
        self.max_points = 500
        self.timestamps = deque(maxlen=self.max_points)
        self.flow_rates = deque(maxlen=self.max_points)
        
        # Current values
        self.current_flow = 0.0
        self.total_volume = 0.0
        self.min_flow = float('inf')
        self.max_flow = float('-inf')
        self.avg_flow = 0.0
        
        # UI elements
        self.window = None
        self.connect_btn = None
        self.status_label = None
        self.flow_label = None
        self.min_label = None
        self.max_label = None
        self.avg_label = None
        self.volume_label = None
        self.color = None
        
        # Graph elements
        self.graph_frame = None
        self.fig = None
        self.ax = None
        self.canvas = None
        
        # BLE Characteristics
        self.SERVICE_UUID = "12345678-0000-1000-8000-00805f9b34fb"
        self.FLOW_UUID = "12345678-0001-1000-8000-00805f9b34fb"
        self.TOTAL_UUID = "12345678-0002-1000-8000-00805f9b34fb"

class MultiDeviceFlowDashboard:
    def __init__(self, root):
        print("Initializing dashboard...")
        self.root = root
        self.root.title("ESP32 BLE Multi-Device Flow Scanner - Main Control")
        self.root.geometry("800x400")
        
        # Device management
        self.devices = {}
        self.next_device_id = 1
        self.available_devices = []
        
        # Graph colors
        self.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
                       '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        self.color_index = 0
        
        # Async loop
        self.loop = None
        self.loop_thread = None
        
        # Animation
        self.animation_running = False
        
        # CSV logging
        self.log_dir = r"C:\path\to\your\logs"
        os.makedirs(self.log_dir, exist_ok=True)
        
        self.global_logging = False
        self.global_csv_file = None
        self.global_csv_writer = None
        self.global_log_path = None
        self.last_log_time = None
        
        self.setup_ui()
        self.start_async_loop()
        print("Dashboard initialized!")
        
    def setup_ui(self):
        print("Setting up UI...")
        # Device Management Frame
        mgmt_frame = ttk.LabelFrame(self.root, text="Device Management", padding=10)
        mgmt_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(mgmt_frame, text="Scan for BLE Devices", 
                  command=self.scan_devices).pack(side="left", padx=5)
        
        ttk.Label(mgmt_frame, text="Available Devices:").pack(side="left", padx=(20, 5))
        self.device_combo = ttk.Combobox(mgmt_frame, width=40, state="readonly")
        self.device_combo.pack(side="left", padx=5)
        
        ttk.Button(mgmt_frame, text="Add Device", 
                  command=self.add_device).pack(side="left", padx=5)
        
        self.scan_status_label = ttk.Label(mgmt_frame, text="Ready to scan", foreground="gray")
        self.scan_status_label.pack(side="left", padx=10)
        
        # Global Logging Frame
        logging_frame = ttk.LabelFrame(self.root, text="Data Logging (All Devices)", padding=10)
        logging_frame.pack(fill="x", padx=10, pady=5)
        
        self.global_log_btn = ttk.Button(logging_frame, text="Start Logging All", 
                                         command=self.toggle_global_logging,
                                         state="disabled")
        self.global_log_btn.pack(side="left", padx=5)
        
        self.global_log_status = ttk.Label(logging_frame, text="No devices connected", foreground="gray")
        self.global_log_status.pack(side="left", padx=10)
        
        ttk.Label(logging_frame, text="CSV Format: One row per timestamp with columns for each device", 
                 font=("Arial", 9, "italic")).pack(side="left", padx=20)
        
        # Active Devices Frame
        devices_frame = ttk.LabelFrame(self.root, text="Active Devices", padding=10)
        devices_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        list_container = ttk.Frame(devices_frame)
        list_container.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side="right", fill="y")
        
        self.device_listbox = tk.Listbox(list_container, height=8, font=("Arial", 10),
                                         yscrollcommand=scrollbar.set)
        self.device_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.device_listbox.yview)
        
        # Event Log Frame
        log_frame = ttk.LabelFrame(self.root, text="Event Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill="both", expand=True)
        
        self.log_text = tk.Text(log_container, height=6, wrap="word", font=("Courier", 9))
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar = ttk.Scrollbar(log_container, command=self.log_text.yview)
        log_scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        
    def start_async_loop(self):
        """Start asyncio event loop in separate thread"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        self.log_message("Async event loop started")
        
    def scan_devices(self):
        """Scan for BLE devices"""
        self.scan_status_label.config(text="Scanning...", foreground="blue")
        self.log_message("Starting BLE scan (filtering for FLOW_LOGGER_ devices)...")
        
        async def scan():
            try:
                devices = await BleakScanner.discover(timeout=5.0)
                
                filtered_devices = [
                    (d.address, d.name) for d in devices 
                    if d.name and "FLOW_LOGGER_" in d.name
                ]
                
                self.available_devices = filtered_devices
                
                device_list = [f"{name} ({addr})" for addr, name in self.available_devices]
                self.root.after(0, lambda: self.device_combo.config(values=device_list))
                
                if device_list:
                    self.root.after(0, lambda: self.device_combo.current(0))
                    self.root.after(0, lambda: self.scan_status_label.config(
                        text=f"Found {len(device_list)} FLOW_LOGGER devices", foreground="green"))
                    self.log_message(f"Found {len(device_list)} FLOW_LOGGER devices")
                else:
                    self.root.after(0, lambda: self.scan_status_label.config(
                        text="No FLOW_LOGGER devices found", foreground="orange"))
                    self.log_message("No FLOW_LOGGER devices found in scan")
                    
            except Exception as e:
                self.log_message(f"Scan error: {str(e)}")
                self.root.after(0, lambda: self.scan_status_label.config(
                    text="Scan failed", foreground="red"))
        
        asyncio.run_coroutine_threadsafe(scan(), self.loop)
        
    def add_device(self):
        """Add a new flow device"""
        if not self.available_devices:
            messagebox.showwarning("No Devices", "Please scan for devices first!")
            return
            
        selection = self.device_combo.current()
        if selection < 0:
            messagebox.showwarning("No Selection", "Please select a device from the list!")
            return
            
        address, name = self.available_devices[selection]
        
        for device in self.devices.values():
            if device.address == address:
                messagebox.showwarning("Duplicate Device", 
                                     f"Device {name} is already added!")
                return
        
        device_id = self.next_device_id
        self.next_device_id += 1
        
        device = FlowDevice(device_id, name, address)
        device.color = self.colors[self.color_index % len(self.colors)]
        self.color_index += 1
        
        self.devices[device_id] = device
        self.create_device_window(device)
        self.update_device_list()
        
        self.log_message(f"Added Device {device_id}: {name} ({address})")
        
    def create_device_window(self, device):
        """Create a separate window for a device"""
        device.window = tk.Toplevel(self.root)
        device.window.title(f"{device.device_name}")
        device.window.geometry("800x650")
        device.window.protocol("WM_DELETE_WINDOW", lambda: self.close_device_window(device.device_id))
        
        main_frame = ttk.Frame(device.window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Control row - compact
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill="x", pady=(0, 5))
        
        device.connect_btn = ttk.Button(control_frame, text="Connect", 
                                       command=lambda: self.toggle_connection(device.device_id))
        device.connect_btn.pack(side="left", padx=5)
        
        device.status_label = ttk.Label(control_frame, text="Disconnected", foreground="red", font=("Arial", 9))
        device.status_label.pack(side="left", padx=10)
        
        color_canvas = tk.Canvas(control_frame, width=15, height=15, bg=device.color, 
                                highlightthickness=1, highlightbackground="gray")
        color_canvas.pack(side="left", padx=10)
        
        device.reset_btn = ttk.Button(control_frame, text="Reset Stats", 
                                      command=lambda: self.reset_device_stats(device.device_id))
        device.reset_btn.pack(side="left", padx=5)
        
        ttk.Label(control_frame, text=f"Address: {device.address}", 
                 font=("Courier", 8)).pack(side="left", padx=20)
        
        # Stats frame - compact single row
        stats_frame = ttk.LabelFrame(main_frame, text="Statistics", padding=5)
        stats_frame.pack(fill="x", pady=(0, 5))
        
        # All stats in one compact row
        ttk.Label(stats_frame, text="Flow:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", padx=3)
        device.flow_label = ttk.Label(stats_frame, text="-- L/min", font=("Arial", 9))
        device.flow_label.grid(row=0, column=1, sticky="w", padx=3)
        
        ttk.Label(stats_frame, text="Total:", font=("Arial", 9, "bold")).grid(row=0, column=2, sticky="w", padx=(15, 3))
        device.volume_label = ttk.Label(stats_frame, text="-- L", font=("Arial", 9))
        device.volume_label.grid(row=0, column=3, sticky="w", padx=3)
        
        ttk.Label(stats_frame, text="Min:", font=("Arial", 9, "bold")).grid(row=0, column=4, sticky="w", padx=(15, 3))
        device.min_label = ttk.Label(stats_frame, text="-- L/min", font=("Arial", 9))
        device.min_label.grid(row=0, column=5, sticky="w", padx=3)
        
        ttk.Label(stats_frame, text="Max:", font=("Arial", 9, "bold")).grid(row=0, column=6, sticky="w", padx=(15, 3))
        device.max_label = ttk.Label(stats_frame, text="-- L/min", font=("Arial", 9))
        device.max_label.grid(row=0, column=7, sticky="w", padx=3)
        
        ttk.Label(stats_frame, text="Avg:", font=("Arial", 9, "bold")).grid(row=0, column=8, sticky="w", padx=(15, 3))
        device.avg_label = ttk.Label(stats_frame, text="-- L/min", font=("Arial", 9))
        device.avg_label.grid(row=0, column=9, sticky="w", padx=3)
        
        # Graph frame - takes up all remaining space
        device.graph_frame = ttk.LabelFrame(main_frame, text=f"Live Flow Rate", padding=5)
        device.graph_frame.pack(fill="both", expand=True)
        
    def close_device_window(self, device_id):
        """Handle closing a device window"""
        if device_id not in self.devices:
            return
            
        device = self.devices[device_id]
        
        if device.connected:
            response = messagebox.askyesno("Device Connected", 
                                          f"{device.device_name} is still connected.\n\nDisconnect and close window?")
            if response:
                asyncio.run_coroutine_threadsafe(self.disconnect_device(device_id), self.loop)
            else:
                return
        
        if device.canvas:
            device.canvas.get_tk_widget().destroy()
        if device.fig:
            plt.close(device.fig)
        
        if device.window:
            device.window.destroy()
            device.window = None
        
        del self.devices[device_id]
        self.update_device_list()
        
        if not self.devices and self.animation_running:
            self.stop_animation()
        
        if self.global_logging:
            self.update_csv_header()
        
        self.log_message(f"Closed Device {device_id}")
        
    def update_device_list(self):
        """Update the device listbox"""
        self.device_listbox.delete(0, tk.END)
        for device in self.devices.values():
            status = "Connected" if device.connected else "Disconnected"
            self.device_listbox.insert(tk.END, f"{device.device_name} - {status}")
        
    def toggle_connection(self, device_id):
        """Toggle device connection"""
        if device_id not in self.devices:
            return
            
        device = self.devices[device_id]
        
        if not device.connected:
            asyncio.run_coroutine_threadsafe(self.connect_device(device_id), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.disconnect_device(device_id), self.loop)
            
    async def connect_device(self, device_id):
        """Connect to BLE device"""
        device = self.devices[device_id]
        
        try:
            self.root.after(0, lambda: device.status_label.config(text="Connecting...", foreground="orange"))
            self.log_message(f"Connecting to Device {device_id}...")
            
            device.client = BleakClient(device.address, timeout=20.0)
            await device.client.connect()
            
            if not device.client.is_connected:
                raise Exception("Failed to establish connection")
            
            self.log_message(f"✓ Connected to Device {device_id}")
            
            device.connected = True
            self.root.after(0, lambda: device.connect_btn.config(text="Disconnect"))
            self.root.after(0, lambda: device.status_label.config(text="Connected", foreground="green"))
            self.root.after(0, self.update_device_list)
            
            connected_count = sum(1 for d in self.devices.values() if d.connected)
            if connected_count == 1:
                self.root.after(0, lambda: self.global_log_btn.config(state="normal"))
                self.root.after(0, lambda: self.global_log_status.config(text="Ready to log", foreground="green"))
            
            if self.global_logging:
                self.root.after(0, self.update_csv_header)
            
            await self.start_monitoring(device_id)
            
            self.root.after(0, lambda: self.show_device_graph(device_id))
            if not self.animation_running:
                self.root.after(0, self.start_animation)
            
        except Exception as e:
            self.log_message(f"✗ Connection failed for Device {device_id}: {str(e)}")
            self.root.after(0, lambda: device.status_label.config(text="Failed", foreground="red"))
            
    async def disconnect_device(self, device_id):
        """Disconnect from BLE device"""
        device = self.devices[device_id]
        
        try:
            device.monitoring = False
            
            if device.client and device.client.is_connected:
                await device.client.disconnect()
            
            device.connected = False
            device.client = None
            
            self.root.after(0, lambda: device.connect_btn.config(text="Connect"))
            self.root.after(0, lambda: device.status_label.config(text="Disconnected", foreground="red"))
            self.root.after(0, lambda: self.hide_device_graph(device_id))
            self.root.after(0, self.update_device_list)
            self.log_message(f"Disconnected Device {device_id}")
            
            connected_count = sum(1 for d in self.devices.values() if d.connected)
            if connected_count == 0:
                if self.global_logging:
                    self.root.after(0, self.stop_global_logging)
                self.root.after(0, lambda: self.global_log_btn.config(state="disabled"))
                self.root.after(0, lambda: self.global_log_status.config(text="No devices connected", foreground="gray"))
            
            if self.global_logging:
                self.root.after(0, self.update_csv_header)
            
            if connected_count == 0 and self.animation_running:
                self.root.after(0, self.stop_animation)
            
        except Exception as e:
            self.log_message(f"Disconnect error for Device {device_id}: {str(e)}")
            
    async def start_monitoring(self, device_id):
        """Start monitoring flow data from device"""
        device = self.devices[device_id]
        device.monitoring = True
        
        def flow_handler(sender, data):
            """Handle flow rate notifications"""
            try:
                flow_str = data.decode('utf-8', errors='ignore').strip().rstrip('\x00').strip()
                
                import re
                match = re.search(r'[-+]?\d*\.?\d+', flow_str)
                if match:
                    flow_rate = float(match.group())
                    
                    now = datetime.now()
                    device.timestamps.append(now)
                    device.flow_rates.append(flow_rate)
                    
                    device.current_flow = flow_rate
                    device.min_flow = min(device.min_flow, flow_rate)
                    device.max_flow = max(device.max_flow, flow_rate)
                    
                    if device.flow_rates:
                        device.avg_flow = sum(device.flow_rates) / len(device.flow_rates)
                    
                    self.root.after(0, lambda: self.update_device_display(device_id))
                    
                    if len(device.timestamps) > 1:
                        time_diff = (device.timestamps[-1] - device.timestamps[-2]).total_seconds() / 60.0
                        device.total_volume += flow_rate * time_diff
                    
                    self.log_data_point(now)
                    
            except Exception as e:
                self.log_message(f"Flow parse error Device {device_id}: {str(e)}")
        
        def total_handler(sender, data):
            """Handle total volume notifications"""
            pass  # Ignore ESP32 total
        
        try:
            await device.client.start_notify(device.FLOW_UUID, flow_handler)
            await device.client.start_notify(device.TOTAL_UUID, total_handler)
            self.log_message(f"Started monitoring Device {device_id}")
            
        except Exception as e:
            self.log_message(f"Monitoring start failed Device {device_id}: {str(e)}")
            device.monitoring = False
            
    def update_device_display(self, device_id):
        """Update device statistics display"""
        if device_id not in self.devices:
            return
            
        device = self.devices[device_id]
        
        device.flow_label.config(text=f"{device.current_flow:.2f} L/min")
        device.volume_label.config(text=f"{device.total_volume:.3f} L")
        
        if device.min_flow != float('inf'):
            device.min_label.config(text=f"{device.min_flow:.2f} L/min")
        
        if device.max_flow != float('-inf'):
            device.max_label.config(text=f"{device.max_flow:.2f} L/min")
        
        device.avg_label.config(text=f"{device.avg_flow:.2f} L/min")
    
    def toggle_global_logging(self):
        """Toggle global CSV logging"""
        if not self.global_logging:
            self.start_global_logging()
        else:
            self.stop_global_logging()
    
    def start_global_logging(self):
        """Start global CSV logging"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ALL_DEVICES_{timestamp}.csv"
            self.global_log_path = os.path.join(self.log_dir, filename)
            
            self.global_csv_file = open(self.global_log_path, 'w', newline='')
            self.global_csv_writer = csv.writer(self.global_csv_file)
            
            self.write_csv_header()
            
            self.global_logging = True
            self.last_log_time = None
            self.global_log_btn.config(text="Stop Logging All")
            self.global_log_status.config(text=f"Logging to: {filename}", foreground="blue")
            
            self.log_message(f"Started global CSV logging: {filename}")
            
        except Exception as e:
            messagebox.showerror("Logging Error", f"Failed to start global logging: {str(e)}")
            self.log_message(f"Failed to start global logging: {str(e)}")
    
    def write_csv_header(self):
        """Write CSV header"""
        if not self.global_csv_writer:
            return
        
        header = ['Timestamp']
        
        connected_devices = sorted(
            [d for d in self.devices.values() if d.connected],
            key=lambda x: x.device_id
        )
        
        for device in connected_devices:
            header.extend([
                f"{device.device_name}_Flow(L/min)",
                f"{device.device_name}_Total(L)",
                f"{device.device_name}_Min(L/min)",
                f"{device.device_name}_Max(L/min)",
                f"{device.device_name}_Avg(L/min)"
            ])
        
        self.global_csv_writer.writerow(header)
        self.global_csv_file.flush()
    
    def update_csv_header(self):
        """Update CSV header"""
        if not self.global_logging:
            return
        
        if self.global_csv_file:
            self.global_csv_file.close()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ALL_DEVICES_{timestamp}.csv"
        self.global_log_path = os.path.join(self.log_dir, filename)
        
        self.global_csv_file = open(self.global_log_path, 'w', newline='')
        self.global_csv_writer = csv.writer(self.global_csv_file)
        
        self.write_csv_header()
        
        self.global_log_status.config(text=f"Logging to: {filename}", foreground="blue")
        self.log_message(f"Updated CSV file: {filename}")
    
    def log_data_point(self, timestamp):
        """Log data point to CSV"""
        if not self.global_logging or not self.global_csv_writer:
            return
        
        if self.last_log_time and (timestamp - self.last_log_time).total_seconds() < 0.5:
            return
        
        self.last_log_time = timestamp
        
        try:
            row = [timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]]
            
            connected_devices = sorted(
                [d for d in self.devices.values() if d.connected],
                key=lambda x: x.device_id
            )
            
            for device in connected_devices:
                row.extend([
                    f"{device.current_flow:.2f}",
                    f"{device.total_volume:.3f}",
                    f"{device.min_flow:.2f}" if device.min_flow != float('inf') else "0.00",
                    f"{device.max_flow:.2f}" if device.max_flow != float('-inf') else "0.00",
                    f"{device.avg_flow:.2f}"
                ])
            
            self.global_csv_writer.writerow(row)
            self.global_csv_file.flush()
            
        except Exception as e:
            self.log_message(f"CSV write error: {str(e)}")
    
    def stop_global_logging(self):
        """Stop global CSV logging"""
        try:
            if self.global_csv_file:
                self.global_csv_file.close()
                self.global_csv_file = None
                self.global_csv_writer = None
            
            self.global_logging = False
            self.global_log_btn.config(text="Start Logging All")
            self.global_log_status.config(text="Ready to log", foreground="green")
            
            self.log_message(f"Stopped global CSV logging")
            
            if self.global_log_path:
                self.log_message(f"Log saved to: {self.global_log_path}")
            
        except Exception as e:
            self.log_message(f"Error stopping global logging: {str(e)}")
    
    def reset_device_stats(self, device_id):
        """Reset statistics for a device"""
        if device_id not in self.devices:
            return
            
        device = self.devices[device_id]
        
        response = messagebox.askyesno("Reset Statistics", 
                                       f"Reset all statistics for {device.device_name}?\n\n"
                                       "This will reset:\n"
                                       "- Total volume\n"
                                       "- Min/Max/Avg flow rates\n"
                                       "- Graph data")
        
        if response:
            device.timestamps.clear()
            device.flow_rates.clear()
            device.min_flow = float('inf')
            device.max_flow = float('-inf')
            device.avg_flow = 0.0
            device.total_volume = 0.0
            
            self.update_device_display(device_id)
            
            self.log_message(f"Reset statistics for Device {device_id}")
    
    def show_device_graph(self, device_id):
        """Show graph for device"""
        if device_id not in self.devices:
            return
            
        device = self.devices[device_id]
        
        if device.fig is not None:
            return
        
        device.fig, device.ax = plt.subplots(figsize=(6, 3.5))
        device.fig.tight_layout(pad=2.0)
        device.ax.set_xlabel('Time', fontsize=9)
        device.ax.set_ylabel('Flow Rate (L/min)', fontsize=9)
        device.ax.set_title(f'{device.device_name}', fontsize=10, fontweight='bold')
        device.ax.grid(True, alpha=0.3)
        device.ax.tick_params(labelsize=8)
        
        device.canvas = FigureCanvasTkAgg(device.fig, master=device.graph_frame)
        device.canvas.draw()
        device.canvas.get_tk_widget().pack(fill="both", expand=True)
        
    def hide_device_graph(self, device_id):
        """Hide graph for device"""
        if device_id not in self.devices:
            return
            
        device = self.devices[device_id]
        
        if device.canvas:
            device.canvas.get_tk_widget().destroy()
            device.canvas = None
            
        if device.fig:
            plt.close(device.fig)
            device.fig = None
            device.ax = None
        
    def start_animation(self):
        """Start animation"""
        if self.animation_running:
            return
        
        self.animation_running = True
        self.update_all_graphs()
        
    def stop_animation(self):
        """Stop animation"""
        self.animation_running = False
        
    def update_all_graphs(self):
        """Update all graphs"""
        if not self.animation_running:
            return
        
        for device in self.devices.values():
            if device.connected and device.ax is not None:
                self.update_single_graph(device)
        
        self.root.after(100, self.update_all_graphs)
        
    def update_single_graph(self, device):
        """Update single graph"""
        try:
            device.ax.clear()
            device.ax.set_xlabel('Time', fontsize=9)
            device.ax.set_ylabel('Flow Rate (L/min)', fontsize=9)
            device.ax.set_title(f'{device.device_name}', fontsize=10, fontweight='bold')
            device.ax.grid(True, alpha=0.3)
            device.ax.tick_params(labelsize=8)
            
            if len(device.timestamps) > 1:
                device.ax.plot(device.timestamps, device.flow_rates, 
                             color=device.color, linewidth=2)
                
                device.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
                device.fig.autofmt_xdate(rotation=45, ha='right')
                
                now = datetime.now()
                device.ax.set_xlim(now - timedelta(seconds=60), now)
                
                if device.flow_rates:
                    y_min = min(device.flow_rates)
                    y_max = max(device.flow_rates)
                    y_range = y_max - y_min
                    if y_range > 0:
                        device.ax.set_ylim(y_min - 0.1 * y_range, y_max + 0.1 * y_range)
                    else:
                        device.ax.set_ylim(y_min - 0.5, y_min + 0.5)
            else:
                device.ax.set_xlim(datetime.now() - timedelta(seconds=60), datetime.now())
                device.ax.set_ylim(0, 10)
            
            device.canvas.draw_idle()
            
        except Exception as e:
            self.log_message(f"Graph update error Device {device.device_id}: {str(e)}")
        
    def log_message(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        
    def on_closing(self):
        """Clean up on window close"""
        self.animation_running = False
        
        if self.global_logging:
            self.stop_global_logging()
        
        for device_id in list(self.devices.keys()):
            device = self.devices[device_id]
            if device.connected:
                asyncio.run_coroutine_threadsafe(
                    self.disconnect_device(device_id), self.loop)
            if device.window:
                device.window.destroy()
        
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.root.destroy()

def main():
    print("Creating main window...")
    root = tk.Tk()
    print("Initializing app...")
    app = MultiDeviceFlowDashboard(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    print("Starting main loop...")
    root.mainloop()
    print("Application closed.")

if __name__ == "__main__":
    try:
        print("Script started!")
        main()
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")