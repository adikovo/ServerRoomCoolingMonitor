#!/usr/bin/env python3
"""
Database Initialization Script for Server Room Cooling Monitor

This script creates the SQLite database and tables required for the
Server Room Cooling Monitor system. It initializes the database schema
with proper table structures for storing sensor data and alarm events.

Tables created:
- sensor_data: Stores temperature and humidity readings with timestamps
- alarms: Stores system alarm messages and events with timestamps

Usage: python3 init_db.py
"""

import sqlite3
import os
from datetime import datetime

# Database configuration
DATABASE_FILE = "server_room.db"

def create_database():
    """
    Create the SQLite database and initialize tables.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if database file already exists
        db_exists = os.path.exists(DATABASE_FILE)
        
        print("🗄️  SERVER ROOM COOLING MONITOR - DATABASE INITIALIZATION")
        print("=" * 65)
        
        if db_exists:
            print(f"📁 Database file '{DATABASE_FILE}' already exists")
        else:
            print(f"📁 Creating new database file: '{DATABASE_FILE}'")
        
        # Connect to database (creates file if it doesn't exist)
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            
            print("\n🔧 Creating database tables...")
            
            # Create sensor_data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    temperature REAL NOT NULL,
                    humidity REAL NOT NULL
                )
            ''')
            
            print("✅ Table 'sensor_data' created/verified")
            print("   • id (INTEGER PRIMARY KEY AUTOINCREMENT)")
            print("   • timestamp (DATETIME, default current timestamp)")
            print("   • temperature (REAL)")
            print("   • humidity (REAL)")
            
            # Create alarms table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alarms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    message TEXT NOT NULL
                )
            ''')
            
            print("✅ Table 'alarms' created/verified")
            print("   • id (INTEGER PRIMARY KEY AUTOINCREMENT)")
            print("   • timestamp (DATETIME, default current timestamp)")
            print("   • message (TEXT)")
            
            # Create indexes for better query performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
                ON sensor_data(timestamp)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_alarm_timestamp 
                ON alarms(timestamp)
            ''')
            
            print("✅ Database indexes created for optimal performance")
            
            # Commit the changes
            conn.commit()
            
            # Verify tables were created by querying schema
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('sensor_data', 'alarms')
            ''')
            
            tables = cursor.fetchall()
            table_names = [table[0] for table in tables]
            
            print(f"\n📊 Database schema verification:")
            print(f"   • Tables found: {table_names}")
            
            # Get table info for sensor_data
            cursor.execute("PRAGMA table_info(sensor_data)")
            sensor_columns = cursor.fetchall()
            print(f"   • sensor_data columns: {len(sensor_columns)}")
            
            # Get table info for alarms
            cursor.execute("PRAGMA table_info(alarms)")
            alarm_columns = cursor.fetchall()
            print(f"   • alarms columns: {len(alarm_columns)}")
            
            # Display database file info
            file_size = os.path.getsize(DATABASE_FILE)
            print(f"\n💾 Database file information:")
            print(f"   • File: {DATABASE_FILE}")
            print(f"   • Size: {file_size} bytes")
            print(f"   • Location: {os.path.abspath(DATABASE_FILE)}")
            
            print("\n" + "=" * 65)
            print("🎉 DATABASE INITIALIZATION COMPLETED SUCCESSFULLY!")
            print("=" * 65)
            print("📋 Next steps:")
            print("   1. Run 'python3 data_manager.py' to start the data manager")
            print("   2. Run sensor emulators to populate the database")
            print("   3. Monitor data with your GUI application")
            print("=" * 65)
            
            return True
            
    except sqlite3.Error as e:
        print(f"\n❌ SQLite error occurred: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error occurred: {e}")
        return False

def check_database_status():
    """
    Check the current status of the database and display statistics.
    """
    try:
        if not os.path.exists(DATABASE_FILE):
            print(f"⚠️  Database file '{DATABASE_FILE}' does not exist")
            return
        
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            
            print(f"\n📈 DATABASE STATISTICS:")
            print("-" * 40)
            
            # Count sensor data records
            cursor.execute("SELECT COUNT(*) FROM sensor_data")
            sensor_count = cursor.fetchone()[0]
            print(f"🌡️  Sensor readings: {sensor_count}")
            
            # Count alarm records
            cursor.execute("SELECT COUNT(*) FROM alarms")
            alarm_count = cursor.fetchone()[0]
            print(f"🚨 Alarm events: {alarm_count}")
            
            # Get latest sensor reading
            cursor.execute('''
                SELECT timestamp, temperature, humidity 
                FROM sensor_data 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            
            latest_sensor = cursor.fetchone()
            if latest_sensor:
                print(f"📊 Latest reading: {latest_sensor[1]}°C, {latest_sensor[2]}% at {latest_sensor[0]}")
            else:
                print("📊 No sensor readings found")
            
            # Get latest alarm
            cursor.execute('''
                SELECT timestamp, message 
                FROM alarms 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            
            latest_alarm = cursor.fetchone()
            if latest_alarm:
                print(f"⚠️  Latest alarm: {latest_alarm[1]} at {latest_alarm[0]}")
            else:
                print("⚠️  No alarms found")
                
    except sqlite3.Error as e:
        print(f"❌ Error checking database status: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def main():
    """Main function to initialize the database."""
    print(f"🚀 Starting database initialization at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create database and tables
    success = create_database()
    
    if success:
        # Display current database status
        check_database_status()
        return 0
    else:
        print("\n💥 Database initialization failed!")
        return 1

if __name__ == "__main__":
    exit(main())
