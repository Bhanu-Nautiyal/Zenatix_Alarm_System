import sqlite3
import json
import csv
import time
import paho.mqtt.client as mqtt
from threading import Lock, Thread
from typing import Dict, Optional
from alarm_processor import *
from alarm_rules import *


def get_alarm_rule_from_user():
    """Collect alarm rule details from the user."""
    print("\nEnter details for the new alarm rule:")
    name = input("Alarm Name: ")
    sensor_id = input("Sensor ID (Choose from: temperature, current, humidity): ")
    type = input("Alarm Type (simple/conditional): ").strip().lower()
    primary_threshold = float(input("Primary Threshold: "))
    duration = int(input("Duration (in seconds): "))
    topic = input("MQTT Topic: ")

    # For conditional alarms, collect shunt details
    if type == "conditional":
        shunt_sensor_id = input("Shunt Sensor ID: ")
        shunt_threshold = float(input("Shunt Threshold: "))
    else:
        shunt_sensor_id = None
        shunt_threshold = None

    return AlarmRule(
        name=name,
        sensor_id=sensor_id,
        type=type,
        primary_threshold=primary_threshold,
        duration=duration,
        shunt_sensor_id=shunt_sensor_id,
        shunt_threshold=shunt_threshold,
        topic=topic
    )


def main():
    alarm_system = AlarmSystem("mqtt.eclipseprojects.io")

    print("Welcome to the Alarm System Configuration!")
    while True:
        # Prompt user to add a new alarm rule
        new_rule = get_alarm_rule_from_user()
        alarm_system.add_alarm_rule(new_rule)
        print(f"Alarm rule '{new_rule.name}' added successfully!")

        # Ask if the user wants to add another rule
        add_more = input("Do you want to add another alarm rule? (yes/no): ").strip().lower()
        if add_more != "yes":
            break

    alarm_system.load_alarm_rules()
    setup_subscriber(alarm_system.mqtt_client)

    # For processing the files 
    threads = [
        Thread(target=alarm_system.process_sensor_file, args=("s1_testing.csv", "temperature")),
        Thread(target=alarm_system.process_sensor_file, args=("s2_testing.csv", "current")),
        Thread(target=alarm_system.process_sensor_file, args=("s3_testing.csv", "humidity"))
    ]
    
    for thread in threads:
        thread.start()

    # Waiting for all the threads to get over
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()

