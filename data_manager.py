#!/usr/bin/env python3
"""
Data Manager for Server Room Cooling Monitor

This script serves as the central controller for the IoT monitoring system.
It subscribes to sensor and button MQTT topics, stores data in SQLite database,
implements hysteresis logic for cooling fan control, and publishes relay commands
and alarm messages.

Key Features:
- MQTT communication with sensors and actuators
- SQLite database for data persistence
- Hysteresis logic to prevent relay oscillation
- Alarm generation and publishing
- Comprehensive logging and error handling
"""

import json
import sqlite3
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

# MQTT Connection settings for better stability
MQTT_KEEPALIVE = 60
MQTT_RECONNECT_DELAY_MIN = 1
MQTT_RECONNECT_DELAY_MAX = 30

# MQTT Topics
TOPIC_SENSOR_DHT = "server_room/sensor/dht"
TOPIC_BUTTON = "server_room/control/button"
TOPIC_RELAY = "server_room/control/relay"
TOPIC_ALARM = "server_room/alarm"

# Hysteresis thresholds
TEMP_HIGH_THRESHOLD = 28.0  # °C - Turn ON relay
TEMP_LOW_THRESHOLD = 26.0   # °C - Turn OFF relay
HUMIDITY_HIGH_THRESHOLD = 70.0  # % - Turn ON relay
HUMIDITY_LOW_THRESHOLD = 65.0   # % - Turn OFF relay

# Manual override configuration
MANUAL_OVERRIDE_DURATION = 15  # seconds

# Database configuration
DATABASE_FILE = "server_room_monitor.db"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """Handles SQLite database operations for the monitoring system."""
    
    def __init__(self, db_file: str = DATABASE_FILE):
        """
        Initialize database manager.
        
        Args:
            db_file: Path to SQLite database file
        """
        self.db_file = db_file
        self.init_database()
    
    def init_database(self):
        """Initialize the database and create tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Create sensor_data table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sensor_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        temperature REAL NOT NULL,
                        humidity REAL NOT NULL
                    )
                ''')
                
                # Create alarms table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alarms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        message TEXT NOT NULL
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def store_sensor_data(self, temperature: float, humidity: float) -> bool:
        """
        Store sensor reading in the database.
        
        Args:
            temperature: Temperature reading in Celsius
            humidity: Humidity reading in percentage
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Store timestamp in UTC for consistency
            timestamp = datetime.now(timezone.utc).isoformat()
            
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO sensor_data (timestamp, temperature, humidity)
                    VALUES (?, ?, ?)
                ''', (timestamp, temperature, humidity))
                conn.commit()
                
            logger.debug(f"Stored sensor data: T={temperature}°C, H={humidity}%")
            return True
            
        except Exception as e:
            logger.error(f"Error storing sensor data: {e}")
            return False
    
    def store_alarm(self, message: str) -> bool:
        """
        Store alarm event in the database.
        
        Args:
            message: Alarm message
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Store timestamp in UTC for consistency
            timestamp = datetime.now(timezone.utc).isoformat()
            
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO alarms (timestamp, message)
                    VALUES (?, ?)
                ''', (timestamp, message))
                conn.commit()
                
            logger.debug(f"Stored alarm: {message}")  
            return True
            
        except Exception as e:
            logger.error(f"Error storing alarm: {e}")
            return False
    
    def get_latest_sensor_data(self, limit: int = 10) -> list:
        """
        Retrieve the latest sensor readings.
        
        Args:
            limit: Number of records to retrieve
            
        Returns:
            List of sensor data tuples
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT timestamp, temperature, humidity
                    FROM sensor_data
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error retrieving sensor data: {e}")
            return []


class ServerRoomDataManager:
    """Main data manager for the server room cooling monitor system."""
    
    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT):
        """
        Initialize the data manager.
        
        Args:
            broker: MQTT broker hostname/IP
            port: MQTT broker port
        """
        self.broker = broker
        self.port = port
        self.client = mqtt.Client("IOT_DATA_MANAGER_ADI_7708", clean_session=True)
        
        # Configure client for better stability
        self.client.max_inflight_messages_set(20)
        self.client.max_queued_messages_set(0)
        self.is_connected = False
        
        # System state
        self.relay_status = self._get_last_relay_state()  # Restore from database
        self.last_temperature = None
        self.last_humidity = None
        self.sensor_data_count = 0
        self.alarm_count = 0
        
        # Manual override state
        self.manual_override_active = False
        self.manual_override_end_time = None
        
        # Database manager
        self.db_manager = DatabaseManager()
        
        # Set up MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
        self.client.on_publish = self._on_publish
        
        # Log initial relay status
        print(f"🔄 Initial relay status: {self.relay_status}")
        logger.info(f"Restored relay status from database: {self.relay_status}")
    
    def _get_last_relay_state(self) -> str:
        """
        Get the last known relay state from database.
        
        Returns:
            Last relay state ("ON" or "OFF"), defaults to "OFF"
        """
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT message FROM alarms 
                    WHERE message LIKE '%fan turned%' OR message LIKE '%Manual button toggle%'
                    ORDER BY timestamp DESC 
                    LIMIT 1
                ''')
                
                result = cursor.fetchone()
                if result:
                    message = result[0].lower()
                    if 'fan on' in message or 'turned on' in message:
                        return "ON"
                    elif 'fan off' in message or 'turned off' in message:
                        return "OFF"
                        
        except Exception as e:
            logger.warning(f"Could not retrieve relay state from database: {e}")
            
        # Default to OFF if no state found
        return "OFF"
    
    def _save_relay_state(self, status: str):
        """
        Save current relay state to database for persistence.
        
        Args:
            status: Current relay status ("ON" or "OFF")
        """
        try:
            # This is handled by the existing alarm storage system
            # No additional storage needed as alarms contain relay state changes
            pass
        except Exception as e:
            logger.error(f"Error saving relay state: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            
            # Subscribe to sensor and button topics
            topics = [(TOPIC_SENSOR_DHT, 1), (TOPIC_BUTTON, 1)]
            for topic, qos in topics:
                result = client.subscribe(topic, qos)
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"Subscribed to topic: {topic}")
                else:
                    logger.error(f"Failed to subscribe to topic: {topic}")
                    
            # Publish current relay status to synchronize system
            self._publish_relay_command(self.relay_status)
            print(f"   📤 Published initial relay status: {self.relay_status}")
        else:
            logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.is_connected = False
        if rc != 0:
            logger.warning("Unexpected disconnection from MQTT broker")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback for when the client receives a SUBACK response from the server."""
        logger.debug(f"Subscription confirmed with message ID: {mid}, QoS: {granted_qos}")
    
    def _on_publish(self, client, userdata, mid):
        """Callback for when a message is published."""
        logger.debug(f"Message {mid} published successfully")
    
    def _on_message(self, client, userdata, msg):
        """
        Callback for when a message is received from the broker.
        
        Args:
            client: The client instance
            userdata: User data
            msg: The message instance
        """
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logger.debug(f"Received message on topic '{topic}': {payload}")
            
            if topic == TOPIC_SENSOR_DHT:
                self._handle_sensor_data(payload)
            elif topic == TOPIC_BUTTON:
                self._handle_button_press(payload)
            else:
                logger.warning(f"Received message on unexpected topic: {topic}")
                
        except Exception as e:
            logger.error(f"Error processing received message: {e}")
    
    def _handle_sensor_data(self, payload: str):
        """
        Handle incoming sensor data from DHT sensor.
        
        Args:
            payload: JSON string containing temperature and humidity
        """
        try:
            # Parse JSON data
            data = json.loads(payload)
            temperature = float(data.get('temp', 0))
            humidity = float(data.get('hum', 0))
            
            # Update internal state
            self.last_temperature = temperature
            self.last_humidity = humidity
            self.sensor_data_count += 1
            
            # Print received data
            print(f"\n📊 SENSOR DATA RECEIVED:")
            print(f"   🌡️  Temperature: {temperature}°C")
            print(f"   💧 Humidity: {humidity}%")
            print(f"   ⏰ Time: {datetime.now().strftime('%H:%M:%S')}")
            
            # Store in database
            if self.db_manager.store_sensor_data(temperature, humidity):
                print(f"   💾 Stored in database (#{self.sensor_data_count})")
            else:
                print(f"   ❌ Failed to store in database")
            
            # Apply hysteresis logic (includes manual override check)
            self._apply_hysteresis_logic(temperature, humidity)
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Error parsing sensor data: {e}")
            print(f"❌ Invalid sensor data format: {payload}")
        except Exception as e:
            logger.error(f"Error handling sensor data: {e}")
    
    def _handle_button_press(self, payload: str):
        """
        Handle button press events for manual override.
        
        Args:
            payload: Button event message
        """
        try:
            print(f"\n🔘 BUTTON PRESSED:")
            print(f"   📤 Message: {payload}")
            print(f"   ⏰ Time: {datetime.now().strftime('%H:%M:%S')}")
            
            # Toggle relay control - Manual override
            old_status = self.relay_status
            new_status = "OFF" if self.relay_status == "ON" else "ON"
            
            # Update relay status
            self.relay_status = new_status
            
            print(f"   🔄 Manual toggle: {old_status} → {new_status}")
            
            # Publish relay command
            self._publish_relay_command(new_status)
            
            self._activate_manual_override()
            
            # Create alarm for manual toggle
            alarm_message = f"Manual button toggle: Fan {new_status} (was {old_status}) - Override active for {MANUAL_OVERRIDE_DURATION}s"
            self._publish_alarm(alarm_message)
            
            # Store alarm in database
            self.db_manager.store_alarm(alarm_message)
            
            print(f"   🚨 Manual override: Fan {new_status}")
            
        except Exception as e:
            logger.error(f"Error handling button press: {e}")
    
    def _check_manual_override(self) -> bool:
        """
        Check if manual override is active.
        
        Returns:
            True if manual override is active, False otherwise
        """
        if not self.manual_override_active:
            return False
        
        # Override is active - show remaining time if end time is set
        if self.manual_override_end_time:
            current_time = time.time()
            remaining_time = max(0, int(self.manual_override_end_time - current_time))
            print(f"   🔒 Manual override active ({remaining_time}s remaining)")
        else:
            print(f"   🔒 Manual override active")
            
        return True
    
    def _activate_manual_override(self):
        """Activate manual override for the configured duration."""
        self.manual_override_active = True
        self.manual_override_end_time = time.time() + MANUAL_OVERRIDE_DURATION
        print(f"   🔒 Manual override activated for {MANUAL_OVERRIDE_DURATION} seconds")
        logger.info(f"Manual override activated for {MANUAL_OVERRIDE_DURATION} seconds")
        
        import threading
        def timeout_callback():
            time.sleep(MANUAL_OVERRIDE_DURATION)
            if self.manual_override_active:
                self.manual_override_active = False
                self.manual_override_end_time = None
                print(f"\n⚠️  WARNING: Manual override expired - returning to automatic control")
                print(f"   🔄 System will now resume automatic fan control based on temperature/humidity")
                logger.warning("Manual override period expired, returning to automatic control")
                
                expiry_alarm = "Manual override expired - Automatic control resumed"
                self._publish_alarm(expiry_alarm)
                self.db_manager.store_alarm(expiry_alarm)
        
        timer_thread = threading.Thread(target=timeout_callback, daemon=True)
        timer_thread.start()
    
    def _apply_hysteresis_logic(self, temperature: float, humidity: float):
        """
        Apply hysteresis logic to determine relay state.
        
        Args:
            temperature: Current temperature in Celsius
            humidity: Current humidity in percentage
        """
        try:
            if self._check_manual_override():
                print(f"   ⚡ Relay status: {self.relay_status} (manual override)")
                return
            
            old_status = self.relay_status
            new_status = old_status
            
            # Hysteresis logic
            if self.relay_status == "OFF":
                # Turn ON if temperature OR humidity exceeds high threshold
                if temperature > TEMP_HIGH_THRESHOLD or humidity > HUMIDITY_HIGH_THRESHOLD:
                    new_status = "ON"
                    reason = []
                    if temperature > TEMP_HIGH_THRESHOLD:
                        reason.append(f"temp {temperature}°C > {TEMP_HIGH_THRESHOLD}°C")
                    if humidity > HUMIDITY_HIGH_THRESHOLD:
                        reason.append(f"humidity {humidity}% > {HUMIDITY_HIGH_THRESHOLD}%")
                    trigger_reason = " OR ".join(reason)
                    
            elif self.relay_status == "ON":
                # Turn OFF only if BOTH temperature AND humidity are below low thresholds
                if temperature < TEMP_LOW_THRESHOLD and humidity < HUMIDITY_LOW_THRESHOLD:
                    new_status = "OFF"
                    trigger_reason = f"temp {temperature}°C < {TEMP_LOW_THRESHOLD}°C AND humidity {humidity}% < {HUMIDITY_LOW_THRESHOLD}%"
            
            # Check if relay status changed
            if new_status != old_status:
                self.relay_status = new_status
                print(f"\n⚡ RELAY CONTROL:")
                print(f"   🔄 Status change: {old_status} → {new_status}")
                print(f"   📋 Reason: {trigger_reason}")
                
                # Publish relay command
                self._publish_relay_command(new_status)
                
                # Create and publish alarm
                alarm_message = f"Cooling fan turned {new_status} - {trigger_reason}"
                self._publish_alarm(alarm_message)
                self.db_manager.store_alarm(alarm_message)
                
            else:
                # No change - show current status
                print(f"   ⚡ Relay status: {self.relay_status} (no change)")
                
        except Exception as e:
            logger.error(f"Error in hysteresis logic: {e}")
    
    def _publish_relay_command(self, command: str):
        """
        Publish relay control command to MQTT.
        
        Args:
            command: Relay command ("ON" or "OFF")
        """
        try:
            if not self.is_connected:
                logger.warning("Not connected to MQTT broker. Cannot publish relay command.")
                return False
            
            result = self.client.publish(TOPIC_RELAY, command, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"   📤 Published relay command: {command}")
                logger.info(f"Published relay command: {command}")
                return True
            else:
                logger.error(f"Failed to publish relay command. Return code: {result.rc}")
                print(f"   ❌ Failed to publish relay command")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing relay command: {e}")
            return False
    
    def _publish_alarm(self, message: str):
        """
        Publish alarm message to MQTT.
        
        Args:
            message: Alarm message
        """
        try:
            if not self.is_connected:
                logger.warning("Not connected to MQTT broker. Cannot publish alarm.")
                return False
            
            # Create alarm data with timestamp in UTC
            alarm_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
                "level": "warning"
            }
            
            json_payload = json.dumps(alarm_data)
            result = self.client.publish(TOPIC_ALARM, json_payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"   🚨 Published alarm: {message}")
                logger.info(f"Published alarm: {message}")
                self.alarm_count += 1
                return True
            else:
                logger.error(f"Failed to publish alarm. Return code: {result.rc}")
                print(f"   ❌ Failed to publish alarm")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing alarm: {e}")
            return False
    
    def connect(self) -> bool:
        """
        Connect to the MQTT broker.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, MQTT_KEEPALIVE)
            self.client.loop_start()
            
            # Wait for connection to be established
            timeout = 10  # seconds
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            return self.is_connected
            
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the MQTT broker."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Disconnected from MQTT broker")
        except Exception as e:
            logger.error(f"Error disconnecting from MQTT broker: {e}")
    
    def display_status(self):
        """Display current system status."""
        connection_icon = "🟢" if self.is_connected else "🔴"
        relay_icon = "🟢" if self.relay_status == "ON" else "🔴"
        
        print("\n" + "="*60)
        print("🏢 SERVER ROOM DATA MANAGER STATUS")
        print("="*60)
        print(f"📡 MQTT Connection: {connection_icon} {'Connected' if self.is_connected else 'Disconnected'}")
        print(f"⚡ Relay Status: {relay_icon} {self.relay_status}")
        if self.last_temperature is not None and self.last_humidity is not None:
            print(f"🌡️  Last Temperature: {self.last_temperature}°C")
            print(f"💧 Last Humidity: {self.last_humidity}%")
        print(f"📊 Sensor Readings: {self.sensor_data_count}")
        print(f"🚨 Alarms Generated: {self.alarm_count}")
        print("-"*60)
        print(f"📋 Hysteresis Thresholds:")
        print(f"   🌡️  Temperature: ON>{TEMP_HIGH_THRESHOLD}°C, OFF<{TEMP_LOW_THRESHOLD}°C")
        print(f"   💧 Humidity: ON>{HUMIDITY_HIGH_THRESHOLD}%, OFF<{HUMIDITY_LOW_THRESHOLD}%")
        print("="*60)
    
    def display_instructions(self):
        """Display user instructions."""
        print("\n" + "="*70)
        print("🏢 SERVER ROOM COOLING MONITOR - DATA MANAGER")
        print("="*70)
        print(f"📡 MQTT Broker: {self.broker}:{self.port}")
        print(f"💾 Database: {DATABASE_FILE}")
        print("-"*70)
        print("📢 SUBSCRIBED TOPICS:")
        print(f"   • {TOPIC_SENSOR_DHT} (temperature & humidity)")
        print(f"   • {TOPIC_BUTTON} (manual override)")
        print("📤 PUBLISHED TOPICS:")
        print(f"   • {TOPIC_RELAY} (relay control)")
        print(f"   • {TOPIC_ALARM} (alarm messages)")
        print("-"*70)
        print("🔄 OPERATION:")
        print("   • Processing sensor data and storing in database")
        print("   • Applying hysteresis logic for fan control")
        print("   • Publishing relay commands and alarms")
        print("   • Press Ctrl+C to stop the data manager")
        print("="*70)
        print("🟢 Data manager is running! Processing messages...\n")
    
    def run(self):
        """Run the data manager continuously."""
        logger.info("Starting Server Room Data Manager...")
        
        # Connect to MQTT broker
        if not self.connect():
            logger.error("Failed to connect to MQTT broker. Exiting.")
            print("❌ Failed to connect to MQTT broker!")
            print("   Make sure the MQTT broker is running on localhost:1883")
            return
        
        # Display instructions and initial status
        self.display_instructions()
        self.display_status()
        
        try:
            # Keep the script running to process messages
            while True:
                if not self.is_connected:
                    logger.warning("Connection lost. Attempting to reconnect...")
                    print("\n⚠️  Connection lost. Reconnecting...")
                    if self.connect():
                        print("✅ Reconnected successfully!")
                        self.display_status()
                    else:
                        print("❌ Reconnection failed. Retrying in 5 seconds...")
                        time.sleep(5)
                        continue
                
                # Sleep briefly to prevent high CPU usage
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n\n👋 Received interrupt signal. Shutting down...")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print(f"❌ Unexpected error: {e}")
        finally:
            print(f"\n📊 Final Statistics:")
            print(f"   • Sensor readings processed: {self.sensor_data_count}")
            print(f"   • Alarms generated: {self.alarm_count}")
            print(f"   • Final relay status: {self.relay_status}")
            self.disconnect()
            print("✅ Data manager stopped.")


def main():
    """Main entry point for the data manager."""
    try:
        manager = ServerRoomDataManager()
        manager.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"💥 Fatal error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
