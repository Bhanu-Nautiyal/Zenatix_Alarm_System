import sqlite3
import json
import csv
import time
import paho.mqtt.client as mqtt
from datetime import datetime
from threading import Lock, Thread
from typing import Dict, Optional


# Yha pe mene alarm rule define kr diye hai
class AlarmRule:
    def __init__(self, 
                 id: int = None,
                 name: str = None,
                 sensor_id: str = None,
                 type: str = None,
                 primary_threshold: float = None,
                 duration: int = None,
                 shunt_sensor_id: str = None,
                 shunt_threshold: float = None,
                 topic: str = None):
        self.id = id
        self.name = name
        self.sensor_id = sensor_id
        self.type = type
        self.primary_threshold = primary_threshold
        self.duration = duration
        self.shunt_sensor_id = shunt_sensor_id
        self.shunt_threshold = shunt_threshold
        self.topic = topic

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'sensor_id': self.sensor_id,
            'type': self.type,
            'primary_threshold': self.primary_threshold,
            'duration': self.duration,
            'shunt_sensor_id': self.shunt_sensor_id,
            'shunt_threshold': self.shunt_threshold,
            'topic': self.topic
        }

# This will hold the AlarmState
class AlarmState:
    def __init__(self, rule_id: int):
        self.rule_id = rule_id
        self.start_time: Optional[datetime] = None
        self.last_value: float = 0.0
        self.active: bool = False

class Alarm:
    def __init__(self, 
                 id: int = None,
                 rule_id: int = None,
                 start_time: datetime = None,
                 end_time: datetime = None,
                 status: str = None):
        self.id = id
        self.rule_id = rule_id
        self.start_time = start_time
        self.end_time = end_time
        self.status = status

    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'status': self.status
        }


class AlarmSystem:
    def __init__(self, broker: str):
        self.db = self._init_db()
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.connect(broker, 1883)
        self.mqtt_client.loop_start()
        
        self.lock = Lock()
        self.alarm_states: Dict[int, AlarmState] = {}
        self.sensor_values: Dict[str, float] = {}
        self.alarm_rules: Dict[int, AlarmRule] = {}

    def _init_db(self):
        db = sqlite3.connect('./alarms.db', check_same_thread=False)
        cursor = db.cursor()
        
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS alarm_rules (
                id INTEGER PRIMARY KEY,
                name TEXT,
                sensor_id TEXT,
                type TEXT,
                primary_threshold REAL,
                duration INTEGER,
                shunt_sensor_id TEXT,
                shunt_threshold REAL,
                topic TEXT
            );

            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER,
                start_time DATETIME,
                end_time DATETIME,
                status TEXT,
                FOREIGN KEY(rule_id) REFERENCES alarm_rules(id)
            );
        ''')
        db.commit()
        return db

    def load_alarm_rules(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM alarm_rules")
        
        for row in cursor.fetchall():
            rule = AlarmRule(
                id=row[0], name=row[1], sensor_id=row[2],
                type=row[3], primary_threshold=row[4],
                duration=row[5], shunt_sensor_id=row[6],
                shunt_threshold=row[7], topic=row[8]
            )
            self.alarm_rules[rule.id] = rule

    def add_alarm_rule(self, rule: AlarmRule):
        cursor = self.db.cursor()
        cursor.execute(
            '''INSERT INTO alarm_rules (
                name, sensor_id, type, primary_threshold, duration,
                shunt_sensor_id, shunt_threshold, topic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (rule.name, rule.sensor_id, rule.type, rule.primary_threshold,
             rule.duration, rule.shunt_sensor_id, rule.shunt_threshold, rule.topic)
        )
        self.db.commit()
        
        rule.id = cursor.lastrowid
        self.alarm_rules[rule.id] = rule

    def process_sensor_data(self, sensor_id: str, value: float):
        with self.lock:
            self.sensor_values[sensor_id] = value
            rules = [rule for rule in self.alarm_rules.values() 
                    if rule.sensor_id == sensor_id]

        for rule in rules:
            self.evaluate_alarm(rule, value)

    def evaluate_alarm(self, rule: AlarmRule, value: float):
        with self.lock:
            if rule.id not in self.alarm_states:
                self.alarm_states[rule.id] = AlarmState(rule.id)
            state = self.alarm_states[rule.id]

            exceeded = value > rule.primary_threshold

            if rule.type == "conditional":
                shunt_value = self.sensor_values.get(rule.shunt_sensor_id)
                if not shunt_value or shunt_value <= rule.shunt_threshold:
                    exceeded = False

            if exceeded:
                if not state.active:
                    state.start_time = datetime.now()
                    state.active = True

                duration = (datetime.now() - state.start_time).total_seconds()
                if duration >= float(rule.duration):
                    self.trigger_alarm(rule, state)
            else:
                if state.active:
                    state.active = False
                    self.clear_alarm(rule, state)

            state.last_value = value

    def trigger_alarm(self, rule: AlarmRule, state: AlarmState):
        alarm = Alarm(
            rule_id=rule.id,
            start_time=state.start_time,
            status="ACTIVE"
        )

        cursor = self.db.cursor()
        cursor.execute(
            "INSERT INTO alarms (rule_id, start_time, status) VALUES (?, ?, ?)",
            (alarm.rule_id, alarm.start_time, alarm.status)
        )
        self.db.commit()
        
        alarm.id = cursor.lastrowid
        payload = json.dumps(alarm.to_dict())
        self.mqtt_client.publish(f"{rule.topic}/alarm", payload)

    def clear_alarm(self, rule: AlarmRule, state: AlarmState):
        cursor = self.db.cursor()
        cursor.execute(
            "UPDATE alarms SET end_time = ?, status = ? WHERE rule_id = ? AND status = 'ACTIVE'",
            (datetime.now(), "CLEARED", rule.id)
        )
        self.db.commit()

    def process_sensor_file(self, filename: str, sensor_type: str):
        with open(filename, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            
            for record in reader:
                value = float(record[2])
                sensor_id = {
                    'sensor1': 'temperature',
                    'sensor2': 'current',
                    'sensor3': 'humidity'
                }.get(record[1])
                
                if sensor_id:
                    self.process_sensor_data(sensor_id, value)
                    print(f"Processing {record[1]}: {value:.2f}")
                    time.sleep(1)

def on_message(client, userdata, message):
    alarm = json.loads(message.payload)
    topic_type = message.topic.split('/')[1]
    print(f"{topic_type.capitalize()} Alarm: Rule {alarm['rule_id']}, "
          f"Status: {alarm['status']}, Start: {alarm['start_time']}")

def setup_subscriber(client):
    topics = ["temperature", "conditional", "humidity"]
    for topic in topics:
        client.subscribe(f"alarms/{topic}/#")
    client.on_message = on_message

def main():
    alarm_system = AlarmSystem("mqtt.eclipseprojects.io")

    # Define rules
    temp_rule = AlarmRule(
        name="High Temperature",
        sensor_id="temperature",
        type="simple",
        primary_threshold=21.5,
        duration=2,
        topic="alarms/temperature"
    )

    conditional_rule = AlarmRule(
        name="High Temperature with Current",
        sensor_id="temperature",
        type="conditional",
        primary_threshold=21.5,
        duration=3,
        shunt_sensor_id="current",
        shunt_threshold=0.2,
        topic="alarms/conditional"
    )

    humidity_rule = AlarmRule(
        name="High Humidity",
        sensor_id="humidity",
        type="simple",
        primary_threshold=80,
        duration=2,
        topic="alarms/humidity"
    )

    humidity_cond_rule = AlarmRule(
        name="High Humidity with High Temperature",
        sensor_id="humidity",
        type="conditional",
        primary_threshold=80,
        duration=2,
        shunt_sensor_id="temperature",
        shunt_threshold=22,
        topic="alarms/conditional"
    )

    # Add rules
    for rule in [temp_rule, conditional_rule, humidity_rule, humidity_cond_rule]:
        alarm_system.add_alarm_rule(rule)

    alarm_system.load_alarm_rules()
    setup_subscriber(alarm_system.mqtt_client)

    # Start processing sensor files in separate threads
    threads = [
        Thread(target=alarm_system.process_sensor_file, args=("s1_testing.csv", "temperature")),
        Thread(target=alarm_system.process_sensor_file, args=("s2_testing.csv", "current")),
        Thread(target=alarm_system.process_sensor_file, args=("s3_testing.csv", "humidity"))
    ]
    
    for thread in threads:
        thread.start()

    # Waiting for all the threads to get over !!!
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()

