#!/usr/bin/env python3
"""
Button Emulator for Server Room Cooling Monitor

This script emulates a physical button by listening for Enter key presses in the terminal
and publishing "pressed" events to an MQTT broker. The events are sent to the topic
"server_room/control/button" whenever the user presses Enter.

This simulates a manual override button that could be used to trigger cooling system
actions or acknowledge alarms in the server room monitoring system.
"""

import time
import logging
from typing import Optional
import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "server_room/control/button"
BUTTON_MESSAGE = "pressed"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ButtonEmulator:
    """Emulates a physical button that publishes MQTT messages when activated."""
    
    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT):
        """
        Initialize the button emulator.
        
        Args:
            broker: MQTT broker hostname/IP
            port: MQTT broker port
        """
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.is_connected = False
        self.press_count = 0
        
        # Set up MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
    
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
    
    def publish_button_press(self) -> bool:
        """
        Publish a button press event to the MQTT topic.
        
        Returns:
            True if publish successful, False otherwise
        """
        try:
            if not self.is_connected:
                logger.warning("Not connected to MQTT broker. Attempting to reconnect...")
                if not self.connect():
                    return False
            
            # Increment press counter
            self.press_count += 1
            
            # Publish button press message
            result = self.client.publish(MQTT_TOPIC, BUTTON_MESSAGE, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"\n🔘 BUTTON PRESSED! (#{self.press_count})")
                print(f"📤 Published '{BUTTON_MESSAGE}' to topic '{MQTT_TOPIC}'")
                print(f"⏰ Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"Button press #{self.press_count} published successfully")
                return True
            else:
                logger.error(f"Failed to publish button press. Return code: {result.rc}")
                print("❌ Failed to publish button press message!")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing button press: {e}")
            print(f"❌ Error: {e}")
            return False
    
    def display_instructions(self):
        """Display user instructions for operating the button emulator."""
        print("\n" + "="*60)
        print("🔘 SERVER ROOM BUTTON EMULATOR")
        print("="*60)
        print(f"📡 MQTT Broker: {self.broker}:{self.port}")
        print(f"📢 Topic: {MQTT_TOPIC}")
        print(f"💬 Message: '{BUTTON_MESSAGE}'")
        print("-"*60)
        print("📋 INSTRUCTIONS:")
        print("   • Press ENTER to simulate button press")
        print("   • Type 'quit' or 'exit' to stop the emulator")
        print("   • Press Ctrl+C for emergency exit")
        print("="*60)
        print("🟢 Emulator is ready! Waiting for button presses...\n")
    
    def run(self):
        """Run the button emulator interactively."""
        logger.info("Starting Button Emulator...")
        
        # Connect to MQTT broker
        if not self.connect():
            logger.error("Failed to connect to MQTT broker. Exiting.")
            print("❌ Failed to connect to MQTT broker!")
            print("   Make sure the MQTT broker is running on localhost:1883")
            return
        
        # Display instructions
        self.display_instructions()
        
        try:
            while True:
                try:
                    # Wait for user input
                    user_input = input("Press ENTER to activate button (or 'quit' to exit): ").strip().lower()
                    
                    # Check for exit commands
                    if user_input in ['quit', 'exit', 'q']:
                        print("\n👋 Shutting down button emulator...")
                        break
                    
                    # If user pressed Enter (empty input) or any other text, treat as button press
                    success = self.publish_button_press()
                    
                    if not success:
                        print("⚠️  Button press failed. Check MQTT connection.")
                    
                    print()  # Add spacing for readability
                    
                except EOFError:
                    # Handle Ctrl+D
                    print("\n\n👋 Received EOF. Shutting down...")
                    break
                    
        except KeyboardInterrupt:
            print("\n\n👋 Received interrupt signal. Shutting down...")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print(f"❌ Unexpected error: {e}")
        finally:
            print(f"\n📊 Total button presses: {self.press_count}")
            self.disconnect()
            print("✅ Button emulator stopped.")


def main():
    """Main entry point for the button emulator."""
    try:
        emulator = ButtonEmulator()
        emulator.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"💥 Fatal error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
