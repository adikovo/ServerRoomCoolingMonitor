#!/usr/bin/env python3
"""
Relay Emulator for Server Room Cooling Monitor

This script emulates a relay-controlled cooling fan by subscribing to MQTT commands
on the topic "server_room/control/relay". It listens for "ON" and "OFF" commands
and displays the corresponding fan status.

The relay emulator simulates the physical cooling fan that would be controlled
by the server room monitoring system based on temperature readings and hysteresis logic.
"""

import time
import logging
from typing import Optional
import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "server_room/control/relay"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RelayEmulator:
    """Emulates a relay-controlled cooling fan that responds to MQTT commands."""
    
    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT):
        """
        Initialize the relay emulator.
        
        Args:
            broker: MQTT broker hostname/IP
            port: MQTT broker port
        """
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.is_connected = False
        self.fan_status = "OFF"  # Track current fan status
        self.command_count = 0
        
        # Duplicate message filtering
        self.last_message = None
        self.last_message_time = 0
        
        # Set up MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            
            # Subscribe to the relay control topic
            result = client.subscribe(MQTT_TOPIC, qos=1)
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Subscribed to topic: {MQTT_TOPIC}")
            else:
                logger.error(f"Failed to subscribe to topic: {MQTT_TOPIC}")
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
    
    def _on_message(self, client, userdata, msg):
        """
        Callback for when a message is received from the broker.
        
        Args:
            client: The client instance
            userdata: User data
            msg: The message instance
        """
        try:
            # Decode the message
            topic = msg.topic
            payload = msg.payload.decode('utf-8').strip().upper()
            
            logger.info(f"Received message on topic '{topic}': {payload}")

            # Check for duplicate message (add these lines) TODO remove this
            import time
            current_time = time.time()
            if (self.last_message == payload and 
                current_time - self.last_message_time < 1.0):  # 1 second window
                logger.debug(f"Duplicate message filtered: {payload}")
                return  # Skip processing duplicate
                
            # Update last message tracking
            self.last_message = payload
            self.last_message_time = current_time

            
            # Process relay commands
            if topic == MQTT_TOPIC:
                self._handle_relay_command(payload)
            else:
                logger.warning(f"Received message on unexpected topic: {topic}")
                
        except Exception as e:
            logger.error(f"Error processing received message: {e}")
    
    def _handle_relay_command(self, command: str):
        """
        Handle relay control commands.
        
        Args:
            command: The relay command ("ON" or "OFF")
        """
        try:
            self.command_count += 1
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            
            if command == "ON":
                if self.fan_status != "ON":
                    self.fan_status = "ON"
                    print(f"\n🌀 Relay: Fan ON")
                    print(f"   ⏰ Time: {timestamp}")
                    print(f"   📊 Command #{self.command_count}")
                    logger.info("Cooling fan turned ON")
                else:
                    print(f"\n🔄 Relay: Fan already ON (no change)")
                    print(f"   ⏰ Time: {timestamp}")
                    logger.info("Fan was already ON")
                    
            elif command == "OFF":
                if self.fan_status != "OFF":
                    self.fan_status = "OFF"
                    print(f"\n⏹️  Relay: Fan OFF")
                    print(f"   ⏰ Time: {timestamp}")
                    print(f"   📊 Command #{self.command_count}")
                    logger.info("Cooling fan turned OFF")
                else:
                    print(f"\n🔄 Relay: Fan already OFF (no change)")
                    print(f"   ⏰ Time: {timestamp}")
                    logger.info("Fan was already OFF")
                    
            else:
                print(f"\n❌ Unknown relay command: '{command}'")
                print(f"   ⏰ Time: {timestamp}")
                print(f"   ℹ️  Expected: 'ON' or 'OFF'")
                logger.warning(f"Received unknown relay command: {command}")
            
            # Show current status
            status_icon = "🟢" if self.fan_status == "ON" else "🔴"
            print(f"   {status_icon} Current Status: Fan {self.fan_status}")
            print("-" * 40)
            
        except Exception as e:
            logger.error(f"Error handling relay command '{command}': {e}")
    
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
    
    def display_status(self):
        """Display the current relay and connection status."""
        connection_icon = "🟢" if self.is_connected else "🔴"
        fan_icon = "🟢" if self.fan_status == "ON" else "🔴"
        
        print("\n" + "="*50)
        print("⚡ RELAY EMULATOR STATUS")
        print("="*50)
        print(f"📡 MQTT Connection: {connection_icon} {'Connected' if self.is_connected else 'Disconnected'}")
        print(f"🌀 Cooling Fan: {fan_icon} {self.fan_status}")
        print(f"📊 Commands Received: {self.command_count}")
        print("-"*50)
    
    def display_instructions(self):
        """Display user instructions for the relay emulator."""
        print("\n" + "="*60)
        print("⚡ SERVER ROOM RELAY EMULATOR")
        print("="*60)
        print(f"📡 MQTT Broker: {self.broker}:{self.port}")
        print(f"📢 Subscribed Topic: {MQTT_TOPIC}")
        print(f"🎯 Accepted Commands: 'ON', 'OFF'")
        print("-"*60)
        print("📋 OPERATION:")
        print("   • Listening for relay control messages...")
        print("   • Fan will respond to ON/OFF commands")
        print("   • Press Ctrl+C to stop the emulator")
        print("="*60)
        print("🟢 Relay emulator is running! Waiting for commands...\n")
    
    def run(self):
        """Run the relay emulator continuously."""
        logger.info("Starting Relay Emulator...")
        
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
            # Keep the script running to listen for messages
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
            print(f"   • Total commands processed: {self.command_count}")
            print(f"   • Final fan status: {self.fan_status}")
            self.disconnect()
            print("✅ Relay emulator stopped.")


def main():
    """Main entry point for the relay emulator."""
    try:
        emulator = RelayEmulator()
        emulator.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"💥 Fatal error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
