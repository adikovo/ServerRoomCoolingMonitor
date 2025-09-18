#!/usr/bin/env python3
"""
Button Control Panel GUI for Server Room Cooling Monitor

This PyQt5 application provides a dedicated control panel for manual fan override.
It features a large toggle button, status displays, and configurable MQTT topic
subscription for integration with the server room monitoring system.

Features:
- Large toggle button for manual fan control
- Real-time fan status display
- MQTT connection status indicator
- Editable topic subscription field
- Compact, focused interface
"""

import sys
import json
import time
import logging
from datetime import datetime
from typing import Optional

import paho.mqtt.client as mqtt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QLabel, QPushButton, QLineEdit, QGroupBox, QFrame
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPalette, QIcon

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
DEFAULT_BUTTON_TOPIC = "server_room/control/button"
DEFAULT_RELAY_TOPIC = "server_room/control/relay"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MQTTWorker(QObject):
    """Worker class to handle MQTT operations in a separate thread."""
    
    # Signals for communication with main thread
    connection_changed = pyqtSignal(bool)
    relay_status_changed = pyqtSignal(str)
    message_published = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.connected = False
        self.button_topic = DEFAULT_BUTTON_TOPIC
        self.relay_topic = DEFAULT_RELAY_TOPIC
        
    def setup_mqtt(self):
        """Initialize MQTT client."""
        try:
            self.client = mqtt.Client("IOT_BUTTON_CONTROL_ADI_7708", clean_session=True)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
            self.client.connect(MQTT_BROKER, MQTT_PORT)
            self.client.loop_start()
            
        except Exception as e:
            logger.error(f"Failed to setup MQTT: {e}")
            self.connection_changed.emit(False)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for successful MQTT connection."""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            self.connection_changed.emit(True)
            
            # Subscribe to relay status topic
            client.subscribe(self.relay_topic, qos=1)
            logger.info(f"Subscribed to relay topic: {self.relay_topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")
            self.connection_changed.emit(False)
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection."""
        self.connected = False
        logger.info("Disconnected from MQTT broker")
        self.connection_changed.emit(False)
    
    def _on_message(self, client, userdata, msg):
        """Callback for received MQTT messages."""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8').strip().upper()
            
            if topic == self.relay_topic:
                logger.info(f"Received relay status: {payload}")
                self.relay_status_changed.emit(payload)
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def publish_button_press(self):
        """Publish button press message."""
        if not self.connected or not self.client:
            logger.warning("Cannot publish - not connected to MQTT broker")
            return False
            
        try:
            message = "pressed"
            result = self.client.publish(self.button_topic, message, qos=1)
            
            if result.rc == 0:
                logger.info(f"Published button press to {self.button_topic}")
                self.message_published.emit(f"Button press sent to {self.button_topic}")
                return True
            else:
                logger.error(f"Failed to publish button press: {result.rc}")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing button press: {e}")
            return False
    
    def update_topics(self, button_topic: str, relay_topic: str):
        """Update MQTT topics and resubscribe."""
        old_relay_topic = self.relay_topic
        self.button_topic = button_topic
        self.relay_topic = relay_topic
        
        if self.connected and self.client:
            # Unsubscribe from old topic and subscribe to new one
            if old_relay_topic != relay_topic:
                self.client.unsubscribe(old_relay_topic)
                self.client.subscribe(relay_topic, qos=1)
                logger.info(f"Updated relay subscription: {old_relay_topic} → {relay_topic}")
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()


class ButtonControlPanel(QMainWindow):
    """Main window for the button control panel."""
    
    def __init__(self):
        super().__init__()
        self.mqtt_worker = MQTTWorker()
        self.fan_status = "OFF"
        self.connection_status = False
        self.button_presses = 0
        
        self.init_ui()
        self.setup_mqtt_connections()
        self.setup_timers()
        
        # Start MQTT connection
        self.mqtt_worker.setup_mqtt()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("🔘 Server Room Manual Control")
        self.setFixedSize(400, 450)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ecf0f1;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin: 5px;
                padding-top: 20px;
                background-color: white;
                min-height: 60px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #2c3e50;
                font-size: 12px;
                font-weight: bold;
                background-color: white;
            }
            QLabel {
                color: #2c3e50;
                font-size: 11px;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                font-size: 11px;
                background-color: #ffffff;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Title
        title = QLabel("🔘 Manual Control")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin: 5px 0px 10px 0px; font-size: 14px;")
        layout.addWidget(title)
        
        # Connection Status
        self.create_connection_status_group(layout)
        
        # Topic Configuration
        self.create_topic_config_group(layout)
        
        # Control Panel
        self.create_control_panel_group(layout)
        
        # Status Display
        self.create_status_display_group(layout)
        
        layout.addStretch()
    
    def create_connection_status_group(self, parent_layout):
        """Create connection status display."""
        group = QGroupBox("🌐 Connection Status")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(5)
        
        self.connection_label = QLabel("🔴 Disconnected")
        self.connection_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.connection_label.setAlignment(Qt.AlignCenter)
        self.connection_label.setStyleSheet("color: #e74c3c; padding: 8px; font-size: 12px;")
        
        layout.addWidget(self.connection_label)
        parent_layout.addWidget(group)
    
    def create_topic_config_group(self, parent_layout):
        """Create topic configuration section."""
        group = QGroupBox("📡 Topic")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(6)
        
        # Horizontal layout for input and button
        input_layout = QHBoxLayout()
        
        # Button topic input with placeholder
        self.button_topic_input = QLineEdit()
        self.button_topic_input.setPlaceholderText(DEFAULT_BUTTON_TOPIC)
        self.button_topic_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 8px;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                font-size: 11px;
                background-color: #ffffff;
                font-family: 'Courier New', monospace;
                color: #2c3e50;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
            }
            QLineEdit::placeholder {
                color: #7f8c8d;
                font-style: italic;
            }
        """)
        input_layout.addWidget(self.button_topic_input, 1)
        
        # Smaller update button
        update_btn = QPushButton("Update")
        update_btn.setFixedSize(60, 28)
        update_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #545b62;
            }
            QPushButton:pressed {
                background-color: #495057;
            }
        """)
        update_btn.clicked.connect(self.update_topic)
        input_layout.addWidget(update_btn)
        
        layout.addLayout(input_layout)
        parent_layout.addWidget(group)
    
    def create_control_panel_group(self, parent_layout):
        """Create main control panel with big button."""
        group = QGroupBox("🎮 Manual Control")
        layout = QVBoxLayout(group)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 18)
        
        # Big toggle button
        self.toggle_button = QPushButton("🟢 TURN ON FAN")
        self.toggle_button.setFont(QFont("Arial", 13, QFont.Bold))
        self.toggle_button.setFixedSize(180, 50)
        # Initial styling will be set in update_button_appearance method
        self.toggle_button.clicked.connect(self.toggle_fan)
        self.toggle_button.setEnabled(False)  # Disabled until connected
        
        layout.addWidget(self.toggle_button, alignment=Qt.AlignCenter)
        parent_layout.addWidget(group)
    
    def create_status_display_group(self, parent_layout):
        """Create status display section."""
        group = QGroupBox("📊 Status")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 8, 12, 12)
        
        # Fan status row
        fan_row = QHBoxLayout()
        fan_label = QLabel("Fan:")
        fan_label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 11px;")
        fan_label.setFixedWidth(60)
        fan_row.addWidget(fan_label)
        
        self.fan_status_label = QLabel("🔴 OFF")
        self.fan_status_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.fan_status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        fan_row.addWidget(self.fan_status_label)
        fan_row.addStretch()
        layout.addLayout(fan_row)
        
        # Button presses row
        press_row = QHBoxLayout()
        press_label = QLabel("Presses:")
        press_label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 11px;")
        press_label.setFixedWidth(60)
        press_row.addWidget(press_label)
        
        self.button_count_label = QLabel("0")
        self.button_count_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.button_count_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        press_row.addWidget(self.button_count_label)
        press_row.addStretch()
        layout.addLayout(press_row)
        
        parent_layout.addWidget(group)
    
    def setup_mqtt_connections(self):
        """Setup MQTT worker signal connections."""
        self.mqtt_worker.connection_changed.connect(self.on_connection_changed)
        self.mqtt_worker.relay_status_changed.connect(self.on_relay_status_changed)
        self.mqtt_worker.message_published.connect(self.on_message_published)
    
    def setup_timers(self):
        """Setup periodic timers."""
        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_display)
        self.status_timer.start(1000)  # Update every second
    
    def on_connection_changed(self, connected: bool):
        """Handle MQTT connection status change."""
        self.connection_status = connected
        
        if connected:
            self.connection_label.setText("🟢 Connected")
            self.connection_label.setStyleSheet("color: #28a745;")
            self.toggle_button.setEnabled(True)
            self.update_button_appearance()
        else:
            self.connection_label.setText("🔴 Disconnected")
            self.connection_label.setStyleSheet("color: #e74c3c;")
            self.toggle_button.setEnabled(False)
    
    def on_relay_status_changed(self, status: str):
        """Handle relay status change from MQTT."""
        self.fan_status = status
        
        if status == "ON":
            self.fan_status_label.setText("🟢 ON")
            self.fan_status_label.setStyleSheet("color: #28a745;")
        else:
            self.fan_status_label.setText("🔴 OFF")
            self.fan_status_label.setStyleSheet("color: #e74c3c;")
            
        # Update button appearance based on fan status
        self.update_button_appearance()
    
    def on_message_published(self, message: str):
        """Handle successful message publication."""
        pass  # No longer displaying last action
    
    def toggle_fan(self):
        """Handle toggle button press."""
        if not self.connection_status:
            return
            
        success = self.mqtt_worker.publish_button_press()
        if success:
            self.button_presses += 1
            self.button_count_label.setText(str(self.button_presses))
    
    def update_topic(self):
        """Update MQTT button topic."""
        button_topic = self.button_topic_input.text().strip()
        
        # Use default topic if input is empty
        if not button_topic:
            button_topic = DEFAULT_BUTTON_TOPIC
            
        self.mqtt_worker.update_topics(button_topic, DEFAULT_RELAY_TOPIC)
        # Clear the input to show placeholder again
        self.button_topic_input.clear()
    
    def update_button_appearance(self):
        """Update button appearance based on fan status."""
        if self.fan_status == "ON":
            # Fan is ON - show red button to turn OFF
            self.toggle_button.setText("🔴 TURN OFF FAN")
            self.toggle_button.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
                QPushButton:pressed {
                    background-color: #bd2130;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #7f8c8d;
                }
            """)
        else:
            # Fan is OFF - show green button to turn ON
            self.toggle_button.setText("🟢 TURN ON FAN")
            self.toggle_button.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
                QPushButton:pressed {
                    background-color: #1e7e34;
                }
                QPushButton:disabled {
                    background-color: #95a5a6;
                    color: #7f8c8d;
                }
            """)
    
    def update_display(self):
        """Update display elements periodically."""
        # Update window title with connection status
        status_icon = "🟢" if self.connection_status else "🔴"
        self.setWindowTitle(f"{status_icon} Server Room Manual Control")
        
        # Ensure button appearance is correct
        self.update_button_appearance()
    
    def closeEvent(self, event):
        """Handle window close event."""
        logger.info("Shutting down button control panel...")
        self.mqtt_worker.disconnect()
        event.accept()


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Server Room Button Control")
    app.setApplicationVersion("1.0")
    
    # Create and show main window
    window = ButtonControlPanel()
    window.show()
    
    # Center window on screen
    screen = app.desktop().screenGeometry()
    size = window.geometry()
    window.move(
        (screen.width() - size.width()) // 2,
        (screen.height() - size.height()) // 2
    )
    
    logger.info("Button Control Panel started")
    
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
