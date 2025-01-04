import sqlite3
import csv
import time
import json
import paho.mqtt.client as mqtt
from threading import Lock, Thread
from alarm_rules import *

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

        # clearing any leftover data[This was causing some issue]
        self.clear_states()

    def clear_states(self):
        self.sensor_values.clear()
        self.alarm_states.clear()

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
