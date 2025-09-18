#!/usr/bin/env python3
"""
DHT Sensor Emulator for Server Room Cooling Monitor

This script emulates a DHT22 sensor by publishing simulated temperature and humidity
readings to an MQTT broker. The readings are sent to the topic "server_room/sensor/dht"
in JSON format every 20 seconds.

Temperature range: 20-35°C
Humidity range: 30-80%
"""

import json
import random
import time
import logging
from typing import Dict, Any
import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "server_room/sensor/dht"
PUBLISH_INTERVAL = 20  # seconds

# Sensor ranges
TEMP_MIN = 20.0  # °C
TEMP_MAX = 35.0  # °C
HUMIDITY_MIN = 30.0  # %
HUMIDITY_MAX = 80.0  # %

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DHTEmulator:
    """Emulates a DHT22 temperature and humidity sensor."""
    
    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT):
        """
        Initialize the DHT emulator.
        
        Args:
            broker: MQTT broker hostname/IP
            port: MQTT broker port
        """
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.is_connected = False
        
        # Set up MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        
        # Initialize previous values for smooth transitions
        self.last_temp = random.uniform(TEMP_MIN, TEMP_MAX)
        self.last_humidity = random.uniform(HUMIDITY_MIN, HUMIDITY_MAX)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
        else:
            logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.is_connected = False
        if rc != 0:
            logger.warning("Unexpected disconnection from MQTT broker")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_publish(self, client, userdata, mid):
        """Callback for when a message is published."""
        logger.debug(f"Message {mid} published successfully")
    
    def _generate_sensor_data(self) -> Dict[str, float]:
        """
        Generate realistic temperature and humidity readings.
        
        Returns:
            Dictionary containing temperature and humidity values
        """
        # Generate values with some variation from previous readings for realism
        temp_variation = random.uniform(-2.0, 2.0)
        humidity_variation = random.uniform(-5.0, 5.0)
        
        # Calculate new values
        new_temp = self.last_temp + temp_variation
        new_humidity = self.last_humidity + humidity_variation
        
        # Ensure values stay within realistic bounds
        new_temp = max(TEMP_MIN, min(TEMP_MAX, new_temp))
        new_humidity = max(HUMIDITY_MIN, min(HUMIDITY_MAX, new_humidity))
        
        # Update last values
        self.last_temp = new_temp
        self.last_humidity = new_humidity
        
        return {
            "temp": round(new_temp, 1),
            "hum": round(new_humidity, 1)
        }
    
    def connect(self) -> bool:
        """
        Connect to the MQTT broker.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port)
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
    
    def publish_sensor_data(self) -> bool:
        """
        Generate and publish sensor data to MQTT topic.
        
        Returns:
            True if publish successful, False otherwise
        """
        try:
            if not self.is_connected:
                logger.warning("Not connected to MQTT broker. Attempting to reconnect...")
                if not self.connect():
                    return False
            
            # Generate sensor data
            sensor_data = self._generate_sensor_data()
            
            # Convert to JSON
            json_payload = json.dumps(sensor_data)
            
            # Publish to MQTT topic
            result = self.client.publish(MQTT_TOPIC, json_payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published to {MQTT_TOPIC}: {json_payload}")
                return True
            else:
                logger.error(f"Failed to publish message. Return code: {result.rc}")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing sensor data: {e}")
            return False
    
    def run(self):
        """Run the DHT emulator continuously."""
        logger.info("Starting DHT22 Sensor Emulator...")
        logger.info(f"Temperature range: {TEMP_MIN}°C - {TEMP_MAX}°C")
        logger.info(f"Humidity range: {HUMIDITY_MIN}% - {HUMIDITY_MAX}%")
        logger.info(f"Publishing interval: {PUBLISH_INTERVAL} seconds (20 sec for realistic server room monitoring)")
        logger.info(f"MQTT Topic: {MQTT_TOPIC}")
        
        # Connect to MQTT broker
        if not self.connect():
            logger.error("Failed to connect to MQTT broker. Exiting.")
            return
        
        try:
            while True:
                # Publish sensor data
                success = self.publish_sensor_data()
                
                if not success:
                    logger.warning("Failed to publish sensor data. Retrying in next cycle...")
                
                # Wait for next publish interval
                time.sleep(PUBLISH_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal. Shutting down...")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.disconnect()


def main():
    """Main entry point for the DHT emulator."""
    try:
        emulator = DHTEmulator()
        emulator.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
