#!/usr/bin/env python3
"""
Main GUI for Server Room Cooling Monitor

This PyQt5 application provides a real-time dashboard for monitoring server room
temperature, humidity, cooling fan status, and alarm messages. It subscribes to
MQTT topics for live updates and displays historical data from the SQLite database.

Features:
- Real-time sensor data display (temperature & humidity)
- Cooling fan status monitoring
- Alarm and warning message display
- Historical data table with database integration
- Auto-refreshing dashboard with MQTT integration
"""

import sys
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import paho.mqtt.client as mqtt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QLabel, QTableWidget, QTableWidgetItem, QTextEdit,
    QPushButton, QFrame, QScrollArea, QSplitter, QTabWidget
)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt, QThread
from PyQt5.QtGui import QFont, QPalette, QColor

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

# MQTT Topics
TOPIC_SENSOR_DHT = "server_room/sensor/dht"
TOPIC_RELAY = "server_room/control/relay"
TOPIC_ALARM = "server_room/alarm"

# Database configuration
DATABASE_FILE = "server_room_monitor.db"

# GUI Update intervals
UPDATE_INTERVAL_MS = 1000  # 1 second
HISTORY_UPDATE_INTERVAL_MS = 5000  # 5 seconds


class MQTTWorker(QObject):
    """Worker thread for MQTT communication to avoid blocking the GUI."""
    
    # Define signals for communication with main thread
    sensor_data_received = pyqtSignal(dict)
    relay_status_received = pyqtSignal(str)
    alarm_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        self.client = mqtt.Client()
        self.is_connected = False
        
        # Set up MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.is_connected = True
            self.connection_status_changed.emit(True)
            
            # Subscribe to all topics
            topics = [
                (TOPIC_SENSOR_DHT, 1),
                (TOPIC_RELAY, 1),
                (TOPIC_ALARM, 1)
            ]
            
            for topic, qos in topics:
                client.subscribe(topic, qos)
        else:
            self.is_connected = False
            self.connection_status_changed.emit(False)
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.is_connected = False
        self.connection_status_changed.emit(False)
    
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker."""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            if topic == TOPIC_SENSOR_DHT:
                # Parse sensor data
                data = json.loads(payload)
                self.sensor_data_received.emit(data)
                
            elif topic == TOPIC_RELAY:
                # Relay status message
                self.relay_status_received.emit(payload.upper())
                
            elif topic == TOPIC_ALARM:
                # Parse alarm data
                try:
                    alarm_data = json.loads(payload)
                except json.JSONDecodeError:
                    # Handle simple string alarms
                    alarm_data = {
                        "timestamp": datetime.now().isoformat(),
                        "message": payload,
                        "level": "info"
                    }
                self.alarm_received.emit(alarm_data)
                
        except Exception as e:
            print(f"Error processing MQTT message: {e}")
    
    def connect_to_broker(self):
        """Connect to the MQTT broker."""
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Error connecting to MQTT broker: {e}")
    
    def disconnect_from_broker(self):
        """Disconnect from the MQTT broker."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            print(f"Error disconnecting from MQTT broker: {e}")


class ServerRoomMonitorGUI(QMainWindow):
    """Main GUI application for the Server Room Cooling Monitor."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🏢 Server Room Cooling Monitor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Data storage
        self.current_temperature = 0.0
        self.current_humidity = 0.0
        self.fan_status = "OFF"
        self.mqtt_connected = False
        self.alarm_messages = []
        
        # Duplicate message filtering
        self.last_alarm_message = None
        self.last_alarm_time = 0
        
        # Initialize MQTT worker
        self.mqtt_thread = QThread()
        self.mqtt_worker = MQTTWorker()
        self.mqtt_worker.moveToThread(self.mqtt_thread)
        
        # Connect signals
        self.mqtt_worker.sensor_data_received.connect(self.update_sensor_data)
        self.mqtt_worker.relay_status_received.connect(self.update_fan_status)
        self.mqtt_worker.alarm_received.connect(self.add_alarm_message)
        self.mqtt_worker.connection_status_changed.connect(self.update_connection_status)
        
        # Start MQTT thread
        self.mqtt_thread.started.connect(self.mqtt_worker.connect_to_broker)
        self.mqtt_thread.start()
        
        # Set up UI
        self.init_ui()
        
        # Set up timers for periodic updates
        self.setup_timers()
        
        # Apply styling
        self.apply_styling()
    
    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create header
        header_layout = self.create_header()
        main_layout.addLayout(header_layout)
        
        # Create main content using tabs
        tab_widget = QTabWidget()
        
        # Dashboard tab
        dashboard_tab = self.create_dashboard_tab()
        tab_widget.addTab(dashboard_tab, "📊 Live Dashboard")
        
        # Historical data tab
        history_tab = self.create_history_tab()
        tab_widget.addTab(history_tab, "📈 Historical Data")
        
        # Alarms tab
        alarms_tab = self.create_alarms_tab()
        tab_widget.addTab(alarms_tab, "🚨 Alarms & Warnings")
        
        main_layout.addWidget(tab_widget)
    
    def create_header(self):
        """Create the header section with title and connection status."""
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("🏢 Server Room Cooling Monitor")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50; margin: 10px;")
        
        # Connection status
        self.connection_label = QLabel("🔴 Disconnected")
        self.connection_label.setFont(QFont("Arial", 12))
        self.connection_label.setStyleSheet("color: #e74c3c; margin: 10px;")
        
        # Current time
        self.time_label = QLabel()
        self.time_label.setFont(QFont("Arial", 12))
        self.time_label.setStyleSheet("color: #7f8c8d; margin: 10px;")
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.time_label)
        header_layout.addWidget(self.connection_label)
        
        return header_layout
    
    def create_dashboard_tab(self):
        """Create the main dashboard tab."""
        dashboard_widget = QWidget()
        layout = QVBoxLayout(dashboard_widget)
        
        # Current readings section
        readings_frame = self.create_current_readings_frame()
        layout.addWidget(readings_frame)
        
        # System status section
        status_frame = self.create_system_status_frame()
        layout.addWidget(status_frame)
        
        # Recent alarms section
        recent_alarms_frame = self.create_recent_alarms_frame()
        layout.addWidget(recent_alarms_frame)
        
        layout.addStretch()
        return dashboard_widget
    
    def create_current_readings_frame(self):
        """Create frame for current sensor readings."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setStyleSheet("QFrame { border: 2px solid #bdc3c7; border-radius: 10px; margin: 5px; }")
        
        layout = QVBoxLayout(frame)
        
        # Title
        title = QLabel("🌡️ Current Sensor Readings")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Readings layout
        readings_layout = QHBoxLayout()
        
        # Temperature
        temp_layout = QVBoxLayout()
        temp_desc = QLabel("Temperature")
        temp_desc.setFont(QFont("Arial", 12, QFont.Bold))
        temp_desc.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        temp_desc.setAlignment(Qt.AlignCenter)
        
        self.temperature_label = QLabel("--°C")
        self.temperature_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.temperature_label.setStyleSheet("color: #e67e22; text-align: center;")
        self.temperature_label.setAlignment(Qt.AlignCenter)
        
        temp_layout.addWidget(temp_desc)
        temp_layout.addWidget(self.temperature_label)
        
        # Humidity
        humidity_layout = QVBoxLayout()
        humidity_desc = QLabel("Humidity")
        humidity_desc.setFont(QFont("Arial", 12, QFont.Bold))
        humidity_desc.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        humidity_desc.setAlignment(Qt.AlignCenter)
        
        self.humidity_label = QLabel("--%")
        self.humidity_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.humidity_label.setStyleSheet("color: #3498db; text-align: center;")
        self.humidity_label.setAlignment(Qt.AlignCenter)
        
        humidity_layout.addWidget(humidity_desc)
        humidity_layout.addWidget(self.humidity_label)
        
        readings_layout.addLayout(temp_layout)
        readings_layout.addLayout(humidity_layout)
        
        layout.addLayout(readings_layout)
        return frame
    
    def create_system_status_frame(self):
        """Create frame for system status."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setStyleSheet("QFrame { border: 2px solid #bdc3c7; border-radius: 10px; margin: 5px; }")
        
        layout = QVBoxLayout(frame)
        
        # Title
        title = QLabel("⚡ System Status")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Status layout
        status_layout = QHBoxLayout()
        
        # Fan status
        fan_layout = QVBoxLayout()
        fan_desc = QLabel("Cooling Fan")
        fan_desc.setFont(QFont("Arial", 12, QFont.Bold))
        fan_desc.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        fan_desc.setAlignment(Qt.AlignCenter)
        
        self.fan_status_label = QLabel("🔴 OFF")
        self.fan_status_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.fan_status_label.setAlignment(Qt.AlignCenter)
        self.fan_status_label.setStyleSheet("color: #e74c3c; text-align: center;")
        
        fan_layout.addWidget(fan_desc)
        fan_layout.addWidget(self.fan_status_label)
        
        # Database stats
        stats_layout = QVBoxLayout()
        stats_desc = QLabel("Database Records")
        stats_desc.setFont(QFont("Arial", 12, QFont.Bold))
        stats_desc.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        stats_desc.setAlignment(Qt.AlignCenter)
        
        self.db_stats_label = QLabel("📊 Loading...")
        self.db_stats_label.setFont(QFont("Arial", 12))
        self.db_stats_label.setStyleSheet("color: #7f8c8d;")
        self.db_stats_label.setAlignment(Qt.AlignCenter)
        
        stats_layout.addWidget(stats_desc)
        stats_layout.addWidget(self.db_stats_label)
        
        status_layout.addLayout(fan_layout)
        status_layout.addLayout(stats_layout)
        
        layout.addLayout(status_layout)
        return frame
    
    def create_recent_alarms_frame(self):
        """Create frame for recent alarms."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setStyleSheet("QFrame { border: 2px solid #bdc3c7; border-radius: 10px; margin: 5px; }")
        
        layout = QVBoxLayout(frame)
        
        # Title
        title = QLabel("🚨 Recent Alarms")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Alarms text area
        self.recent_alarms_text = QTextEdit()
        self.recent_alarms_text.setMaximumHeight(150)
        self.recent_alarms_text.setReadOnly(True)
        self.recent_alarms_text.setStyleSheet("""
            QTextEdit {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Courier New', monospace;
                color: #2c3e50;
            }
        """)
        
        layout.addWidget(self.recent_alarms_text)
        return frame
    
    def create_history_tab(self):
        """Create the historical data tab."""
        history_widget = QWidget()
        layout = QVBoxLayout(history_widget)
        
        # Title
        title = QLabel("📈 Historical Sensor Data")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin: 10px;")
        layout.addWidget(title)
        
        # Historical data table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["ID", "Timestamp", "Temperature (°C)", "Humidity (%)"])
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #bdc3c7;
                background-color: white;
                color: #2c3e50;
            }
            QTableWidget::item {
                padding: 5px;
                color: #2c3e50;
                border-bottom: 1px solid #ecf0f1;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 5px;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.history_table)
        
        # Refresh button
        refresh_button = QPushButton("🔄 Refresh Data")
        refresh_button.clicked.connect(self.load_historical_data)
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        layout.addWidget(refresh_button)
        
        return history_widget
    
    def create_alarms_tab(self):
        """Create the alarms tab."""
        alarms_widget = QWidget()
        layout = QVBoxLayout(alarms_widget)
        
        # Title
        title = QLabel("🚨 Alarm History")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin: 10px;")
        layout.addWidget(title)
        
        # Alarms table
        self.alarms_table = QTableWidget()
        self.alarms_table.setColumnCount(3)
        self.alarms_table.setHorizontalHeaderLabels(["ID", "Timestamp", "Message"])
        self.alarms_table.setAlternatingRowColors(True)
        self.alarms_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #bdc3c7;
                background-color: white;
                color: #2c3e50;
            }
            QTableWidget::item {
                padding: 5px;
                color: #2c3e50;
                border-bottom: 1px solid #ecf0f1;
            }
            QTableWidget::item:selected {
                background-color: #e74c3c;
                color: white;
            }
            QHeaderView::section {
                background-color: #e74c3c;
                color: white;
                padding: 5px;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.alarms_table)
        
        # Clear alarms button
        clear_button = QPushButton("🗑️ Clear Display")
        clear_button.clicked.connect(self.clear_alarm_display)
        clear_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        layout.addWidget(clear_button)
        
        return alarms_widget
    
    def setup_timers(self):
        """Set up periodic update timers."""
        # Timer for updating current time
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time_display)
        self.time_timer.start(1000)  # Update every second
        
        # Timer for updating database stats
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_database_stats)
        self.stats_timer.start(HISTORY_UPDATE_INTERVAL_MS)
        
        # Timer for loading historical data
        self.history_timer = QTimer()
        self.history_timer.timeout.connect(self.load_historical_data)
        self.history_timer.start(HISTORY_UPDATE_INTERVAL_MS)
        
        # Timer for loading alarms data
        self.alarms_timer = QTimer()
        self.alarms_timer.timeout.connect(self.load_alarms_data)
        self.alarms_timer.start(HISTORY_UPDATE_INTERVAL_MS)
    
    def apply_styling(self):
        """Apply overall styling to the application."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ecf0f1;
            }
            QTabWidget::pane {
                border: 1px solid #bdc3c7;
                background-color: white;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background-color: #95a5a6;
                color: white;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #34495e;
            }
            QTabBar::tab:hover {
                background-color: #7f8c8d;
            }
        """)
    
    def update_sensor_data(self, data):
        """Update sensor data display."""
        try:
            self.current_temperature = float(data.get('temp', 0))
            self.current_humidity = float(data.get('hum', 0))
            
            # Update temperature display with color coding
            temp_color = self.get_temperature_color(self.current_temperature)
            self.temperature_label.setText(f"{self.current_temperature:.1f}°C")
            self.temperature_label.setStyleSheet(f"color: {temp_color}; text-align: center;")
            
            # Update humidity display with color coding
            humidity_color = self.get_humidity_color(self.current_humidity)
            self.humidity_label.setText(f"{self.current_humidity:.1f}%")
            self.humidity_label.setStyleSheet(f"color: {humidity_color}; text-align: center;")
            
        except Exception as e:
            print(f"Error updating sensor data: {e}")
    
    def update_fan_status(self, status):
        """Update fan status display."""
        try:
            self.fan_status = status
            if status == "ON":
                self.fan_status_label.setText("🟢 ON")
                self.fan_status_label.setStyleSheet("color: #27ae60; text-align: center;")
            else:
                self.fan_status_label.setText("🔴 OFF")
                self.fan_status_label.setStyleSheet("color: #e74c3c; text-align: center;")
        except Exception as e:
            print(f"Error updating fan status: {e}")
    
    def add_alarm_message(self, alarm_data):
        """Add new alarm message."""
        try:
            timestamp = alarm_data.get('timestamp', datetime.now().isoformat())
            message = alarm_data.get('message', 'Unknown alarm')
            level = alarm_data.get('level', 'info')
            
            # Check for duplicate alarm messages
            current_time = time.time()
            if (self.last_alarm_message == message and 
                current_time - self.last_alarm_time < 2.0):  # 2 second window
                print(f"Duplicate alarm filtered: {message}")
                return  # Skip duplicate
            
            # Update last alarm tracking
            self.last_alarm_message = message
            self.last_alarm_time = current_time
            
            # Format timestamp for display
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = datetime.now().strftime('%H:%M:%S')
            
            clean_message = self._clean_alarm_message(message)
            
            if "Manual override expired" in message:
                alarm_text = f"[{time_str}] TIMEOUT: {clean_message}"
                self.recent_alarms_text.setTextColor(QColor("#e74c3c"))
                self.recent_alarms_text.append(alarm_text)
                self.recent_alarms_text.setTextColor(QColor("#2c3e50"))
            else:
                alarm_text = f"[{time_str}] {clean_message}"
                self.recent_alarms_text.append(alarm_text)
            
            # Keep only last 10 alarms in recent display
            content = self.recent_alarms_text.toPlainText()
            lines = content.split('\n')
            if len(lines) > 10:
                self.recent_alarms_text.clear()
                self.recent_alarms_text.append('\n'.join(lines[-10:]))
            
            # Store in alarm messages list
            self.alarm_messages.append({
                'timestamp': timestamp,
                'message': message,
                'level': level
            })
            
        except Exception as e:
            print(f"Error adding alarm message: {e}")
    
    def _clean_alarm_message(self, message):
        """Clean up alarm message for better display in GUI."""
        try:
            clean_msg = message.replace('🚨', '').replace('⚠️', '').replace('🔄', '')
            clean_msg = clean_msg.replace('📤', '').replace('🔒', '').replace('⚡', '')
            clean_msg = clean_msg.replace('🌡️', 'Temp').replace('💧', 'Humidity')
            clean_msg = clean_msg.replace('°C', 'C').replace('%', 'pct')
            
            clean_msg = ' '.join(clean_msg.split())
            if "Manual button toggle" in clean_msg:
                parts = clean_msg.split(' - ')
                if len(parts) >= 2:
                    clean_msg = f"Manual: {parts[0].split(':')[1].strip()}"
            elif "Manual override expired" in clean_msg:
                clean_msg = "Manual override expired - Auto control resumed"
            elif "Cooling fan turned" in clean_msg:
                pass  
            
            return clean_msg.strip()
            
        except Exception as e:
            print(f"Error cleaning alarm message: {e}")
            return message
    
    def update_connection_status(self, connected):
        """Update MQTT connection status."""
        self.mqtt_connected = connected
        if connected:
            self.connection_label.setText("🟢 Connected")
            self.connection_label.setStyleSheet("color: #27ae60; margin: 10px;")
        else:
            self.connection_label.setText("🔴 Disconnected")
            self.connection_label.setStyleSheet("color: #e74c3c; margin: 10px;")
    
    def update_time_display(self):
        """Update the current time display."""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.time_label.setText(f"🕐 {current_time}")
    
    def update_database_stats(self):
        """Update database statistics."""
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                
                # Get sensor data count
                cursor.execute("SELECT COUNT(*) FROM sensor_data")
                sensor_count = cursor.fetchone()[0]
                
                # Get alarm count
                cursor.execute("SELECT COUNT(*) FROM alarms")
                alarm_count = cursor.fetchone()[0]
                
                self.db_stats_label.setText(f"📊 {sensor_count} readings\n🚨 {alarm_count} alarms")
                
        except Exception as e:
            self.db_stats_label.setText("📊 Database Error")
            print(f"Error updating database stats: {e}")
    
    def load_historical_data(self):
        """Load historical sensor data from database."""
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, datetime(timestamp, 'localtime') as local_time, 
                           temperature, humidity 
                    FROM sensor_data 
                    ORDER BY timestamp DESC 
                    LIMIT 100
                ''')
                
                data = cursor.fetchall()
                
                self.history_table.setRowCount(len(data))
                
                for row_idx, row_data in enumerate(data):
                    for col_idx, cell_data in enumerate(row_data):
                        if col_idx == 2 or col_idx == 3:  # Temperature and humidity columns
                            cell_data = f"{float(cell_data):.1f}"
                        
                        item = QTableWidgetItem(str(cell_data))
                        self.history_table.setItem(row_idx, col_idx, item)
                
                # Resize columns to content
                self.history_table.resizeColumnsToContents()
                
        except Exception as e:
            print(f"Error loading historical data: {e}")
    
    def load_alarms_data(self):
        """Load alarms data from database."""
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, datetime(timestamp, 'localtime') as local_time, message 
                    FROM alarms 
                    ORDER BY timestamp DESC 
                    LIMIT 50
                ''')
                
                data = cursor.fetchall()
                
                self.alarms_table.setRowCount(len(data))
                
                for row_idx, row_data in enumerate(data):
                    for col_idx, cell_data in enumerate(row_data):
                        item = QTableWidgetItem(str(cell_data))
                        self.alarms_table.setItem(row_idx, col_idx, item)
                
                # Resize columns to content
                self.alarms_table.resizeColumnsToContents()
                
        except Exception as e:
            print(f"Error loading alarms data: {e}")
    
    def clear_alarm_display(self):
        """Clear the alarm display."""
        self.recent_alarms_text.clear()
        self.alarm_messages.clear()
    
    def get_temperature_color(self, temp):
        """Get color for temperature based on value."""
        if temp < 22:
            return "#3498db"  # Blue (cool)
        elif temp < 26:
            return "#27ae60"  # Green (normal)
        elif temp < 30:
            return "#f39c12"  # Orange (warm)
        else:
            return "#e74c3c"  # Red (hot)
    
    def get_humidity_color(self, humidity):
        """Get color for humidity based on value."""
        if humidity < 40:
            return "#e67e22"  # Orange (low)
        elif humidity < 70:
            return "#27ae60"  # Green (normal)
        else:
            return "#3498db"  # Blue (high)
    
    def closeEvent(self, event):
        """Handle application close event."""
        try:
            # Stop MQTT worker
            self.mqtt_worker.disconnect_from_broker()
            self.mqtt_thread.quit()
            self.mqtt_thread.wait()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        event.accept()


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Server Room Cooling Monitor")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("IoT Monitoring Solutions")
    
    # Create and show main window
    try:
        window = ServerRoomMonitorGUI()
        window.show()
        
        # Start the application event loop
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"Fatal error starting application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
