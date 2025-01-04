from datetime import datetime
from typing import Dict, Optional

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
