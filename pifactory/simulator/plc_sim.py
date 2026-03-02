"""PLC Simulator — realistic conveyor/motor tags for Pi-Factory demos.

Simulates an Allen-Bradley Micro 820 controlling a sorting station conveyor.
No SQLite — tags are held in memory and served via the tag_server API.

DemoCycler auto-transitions: normal → warning → fault → recovery on a loop.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import random
from enum import Enum

logger = logging.getLogger(__name__)

ERROR_CODES = {
    0: "No error",
    1: "Motor overload",
    2: "Temperature high",
    3: "Conveyor jam",
    4: "Sensor failure",
    5: "Communication loss",
}

FAULT_MAP = {
    "jam": 3,
    "overload": 1,
    "overheat": 2,
    "sensor": 4,
    "comms": 5,
}


@dataclasses.dataclass
class TagSnapshot:
    """Point-in-time reading of all PLC tags."""

    timestamp: str
    node_id: str
    motor_running: bool
    motor_speed: int
    motor_current: float
    temperature: float
    pressure: int
    conveyor_running: bool
    conveyor_speed: int
    sensor_1: bool
    sensor_2: bool
    fault_alarm: bool
    e_stop: bool
    error_code: int
    error_message: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class PLCSimulator:
    """Simulates a Micro 820 PLC with realistic conveyor behaviour."""

    def __init__(self, node_id: str = "sim-micro820") -> None:
        self.node_id = node_id

        # State
        self.motor_running = True
        self.motor_speed = 60
        self.motor_current = 3.0
        self.temperature = 25.0
        self.pressure = 100
        self.conveyor_running = True
        self.conveyor_speed = 50
        self.sensor_1 = False
        self.sensor_2 = False
        self.fault_alarm = False
        self.e_stop = False
        self.error_code = 0

    def tick(self) -> TagSnapshot:
        """Advance simulation by one step and return the current tag snapshot."""
        # Normal operation: motor current fluctuates with speed
        if self.motor_running and not self.e_stop:
            base_current = self.motor_speed * 0.05
            self.motor_current = round(base_current + random.uniform(-0.3, 0.3), 2)
        else:
            self.motor_current = 0.0

        # Temperature: slowly rises when running, cools when stopped
        if self.motor_running and not self.e_stop:
            if self.temperature < 45.0:
                self.temperature = round(self.temperature + random.uniform(0.05, 0.15), 1)
        else:
            if self.temperature > 22.0:
                self.temperature = round(self.temperature - random.uniform(0.1, 0.3), 1)

        # Sensors: toggle randomly to simulate parts on conveyor
        if self.conveyor_running and not self.e_stop:
            if random.random() < 0.15:
                self.sensor_1 = not self.sensor_1
            if random.random() < 0.10:
                self.sensor_2 = not self.sensor_2
        else:
            self.sensor_1 = False
            self.sensor_2 = False

        # Pressure: mild fluctuation
        self.pressure = max(90, min(110, self.pressure + random.randint(-1, 1)))

        # Fault effects
        if self.error_code == 1:  # Motor overload
            self.motor_current = round(self.motor_speed * 0.12 + random.uniform(0, 1.0), 2)
        elif self.error_code == 2:  # Temperature high
            self.temperature = round(min(95.0, self.temperature + random.uniform(0.5, 1.5)), 1)
        elif self.error_code == 3:  # Conveyor jam
            self.conveyor_speed = 0
            self.sensor_1 = True
            self.motor_current = round(self.motor_speed * 0.10 + random.uniform(0, 0.5), 2)

        snap = TagSnapshot(
            timestamp=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            node_id=self.node_id,
            motor_running=self.motor_running,
            motor_speed=self.motor_speed,
            motor_current=self.motor_current,
            temperature=self.temperature,
            pressure=self.pressure,
            conveyor_running=self.conveyor_running,
            conveyor_speed=self.conveyor_speed if self.error_code != 3 else 0,
            sensor_1=self.sensor_1,
            sensor_2=self.sensor_2,
            fault_alarm=self.fault_alarm,
            e_stop=self.e_stop,
            error_code=self.error_code,
            error_message=ERROR_CODES.get(self.error_code, f"Unknown error {self.error_code}"),
        )
        return snap

    def inject_fault(self, fault_name: str) -> str:
        """Inject a named fault. Returns a status message."""
        if fault_name == "clear":
            self.error_code = 0
            self.fault_alarm = False
            self.conveyor_speed = 50
            return "Faults cleared"
        elif fault_name == "estop":
            self.e_stop = True
            self.motor_running = False
            self.conveyor_running = False
            self.fault_alarm = True
            return "E-STOP activated"
        elif fault_name == "release":
            self.e_stop = False
            self.motor_running = True
            self.conveyor_running = True
            self.motor_speed = 60
            self.conveyor_speed = 50
            self.fault_alarm = False
            self.error_code = 0
            return "E-STOP released, system restarted"
        elif fault_name in FAULT_MAP:
            self.error_code = FAULT_MAP[fault_name]
            self.fault_alarm = True
            msg = ERROR_CODES.get(self.error_code, fault_name)
            return f"Fault injected: {msg} (error_code={self.error_code})"
        else:
            return f"Unknown fault: {fault_name}. Options: {', '.join(list(FAULT_MAP) + ['clear', 'estop', 'release'])}"


class CyclePhase(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    FAULT = "fault"
    RECOVERY = "recovery"


class DemoCycler:
    """Auto-cycles the simulator through phases for hands-free demos.

    Timeline per cycle (60s default):
      0-20s   NORMAL   — healthy tags
      20-30s  WARNING  — temperature creeps up
      30-50s  FAULT    — conveyor jam injected
      50-60s  RECOVERY — faults cleared, cooling down
    """

    def __init__(
        self,
        sim: PLCSimulator,
        cycle_seconds: int = 60,
    ) -> None:
        self.sim = sim
        self.cycle_seconds = cycle_seconds
        self._tick_count = 0
        self._phase = CyclePhase.NORMAL
        self._prev_phase = CyclePhase.NORMAL

    @property
    def phase(self) -> CyclePhase:
        return self._phase

    def tick(self, interval_ms: int = 500) -> TagSnapshot:
        """Advance one tick, auto-transition phases, return snapshot."""
        ticks_per_cycle = self.cycle_seconds * 1000 // interval_ms
        pos = self._tick_count % ticks_per_cycle
        frac = pos / ticks_per_cycle

        self._prev_phase = self._phase

        if frac < 0.33:
            self._phase = CyclePhase.NORMAL
        elif frac < 0.50:
            self._phase = CyclePhase.WARNING
        elif frac < 0.83:
            self._phase = CyclePhase.FAULT
        else:
            self._phase = CyclePhase.RECOVERY

        # Transition logic
        if self._phase != self._prev_phase:
            if self._phase == CyclePhase.NORMAL:
                self.sim.inject_fault("release")
                logger.info("Demo cycle: NORMAL — system healthy")
            elif self._phase == CyclePhase.WARNING:
                self.sim.inject_fault("overheat")
                logger.info("Demo cycle: WARNING — temperature rising")
            elif self._phase == CyclePhase.FAULT:
                self.sim.inject_fault("jam")
                logger.info("Demo cycle: FAULT — conveyor jam")
            elif self._phase == CyclePhase.RECOVERY:
                self.sim.inject_fault("clear")
                logger.info("Demo cycle: RECOVERY — clearing faults")

        self._tick_count += 1
        return self.sim.tick()
