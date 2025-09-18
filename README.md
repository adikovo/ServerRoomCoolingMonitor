# Server Room Cooling Monitor 🌡️

An IoT monitoring system for server room temperature control with automated fan management and manual override capabilities.

## 🚀 Features

- **Real-time monitoring** of temperature and humidity
- **Automated fan control** based on temperature thresholds
- **Manual override** with dedicated control panel
- **Data logging** with SQLite database storage
- **MQTT communication** for wireless device control
- **Hardware emulators** for testing without physical sensors

## 📁 Project Structure

```
├── main_gui.py              # Main monitoring interface
├── button_control_gui.py    # Manual fan control panel
├── data_manager.py          # Database operations
├── init_db.py              # Database initialization
├── emulators/              # Hardware simulation
│   ├── dht_emulator.py     # Temperature/humidity sensor
│   ├── relay_emulator.py   # Fan relay control
│   └── button_emulator.py  # Physical button simulation
└── requirements.txt        # Dependencies
```

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ServerRoomCoolingMonitor.git
cd ServerRoomCoolingMonitor
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the database:
```bash
python init_db.py
```

## 🎯 Usage

### Start the data manager (run first):
```bash
python data_manager.py
```

### Start the main monitoring system:
```bash
python main_gui.py
```

### Launch the manual control panel:
```bash
python button_control_gui.py
```

### Run hardware emulators (for testing):
```bash
python emulators/dht_emulator.py      # Temperature sensor
python emulators/relay_emulator.py    # Fan control
python emulators/button_emulator.py   # Manual button
```

## 🌐 MQTT Configuration

- **Broker**: `broker.hivemq.com:1883`
- **Topics**:
  - Temperature/Humidity: `server_room/sensors/dht`
  - Fan Control: `server_room/control/relay`
  - Manual Button: `server_room/control/button`

## 🔧 Requirements

- Python 3.7+
- PyQt5
- paho-mqtt

## 📊 System Components

- **Main GUI**: Temperature monitoring, data visualization, automatic fan control
- **Control Panel**: Dedicated manual fan override interface  
- **Data Manager**: Handles SQLite database operations, sensor data logging, and MQTT communication coordination
- **Database Init**: Sets up SQLite tables for sensor readings and system events
- **Emulators**: Hardware simulation for development and testing without physical sensors

Built with Python, PyQt5, and MQTT for reliable IoT server room monitoring.