"""Tests for VFDReader — mocks pymodbus, no real Modbus hardware needed."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any, Dict
from unittest import mock

import pytest

from pifactory.hardware.vfd_reader import (
    DEFAULT_REGISTER_MAP,
    VFD_FAULTS,
    VFDReader,
    _load_register_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_mock_client(registers=None, coils=None, connected=True, error=False):
    """Build a mock AsyncModbusTcpClient that returns given register/coil values.

    Args:
        registers: list of raw register values (12 values for addresses 100-111)
        coils: list of bool coil values (1 value for address 0)
        connected: whether the client reports as connected
        error: if True, register reads return error responses
    """
    if registers is None:
        # Default: 45.1 Hz, 50.0 Hz setpoint, 3.2A, 230V, 325V DC bus,
        # 1750 RPM, 65.0% torque, 42.5°C, 1.85kW, fault 0, 10.0s accel, 15.0s decel
        registers = [451, 500, 32, 2300, 3250, 1750, 650, 425, 185, 0, 100, 150]

    if coils is None:
        coils = [True]

    client = mock.AsyncMock()
    client.connected = connected

    # read_holding_registers response
    holding_resp = mock.MagicMock()
    holding_resp.isError.return_value = error
    holding_resp.registers = registers
    client.read_holding_registers = mock.AsyncMock(return_value=holding_resp)

    # read_coils response
    coil_resp = mock.MagicMock()
    coil_resp.isError.return_value = False
    coil_resp.bits = coils
    client.read_coils = mock.AsyncMock(return_value=coil_resp)

    return client


# Patch target: the lazy import inside read_all_tags() does
# `from pymodbus.client import AsyncModbusTcpClient`
# We mock the entire pymodbus.client module so the local import resolves.
_PATCH_TARGET = "pymodbus.client.AsyncModbusTcpClient"


# ---------------------------------------------------------------------------
# Test: Register reading with scaling
# ---------------------------------------------------------------------------

class TestRegisterReading:
    """Verify that raw register values are scaled correctly."""

    def test_reads_all_tags_with_correct_scaling(self):
        reader = VFDReader(host="192.168.1.100", port=502)
        client = _make_mock_client()

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_output_hz"] == 45.1       # 451 * 0.1
        assert tags["vfd_setpoint_hz"] == 50.0      # 500 * 0.1
        assert tags["vfd_output_amps"] == 3.2       # 32 * 0.1
        assert tags["vfd_output_volts"] == 230.0    # 2300 * 0.1
        assert tags["vfd_dc_bus_volts"] == 325.0    # 3250 * 0.1
        assert tags["vfd_motor_rpm"] == 1750        # 1750 * 1
        assert tags["vfd_torque_pct"] == 65.0       # 650 * 0.1
        assert tags["vfd_drive_temp_c"] == 42.5     # 425 * 0.1
        assert tags["vfd_power_kw"] == 1.85         # 185 * 0.01
        assert tags["vfd_fault_code"] == 0          # 0 * 1
        assert tags["vfd_accel_time_sec"] == 10.0   # 100 * 0.1
        assert tags["vfd_decel_time_sec"] == 15.0   # 150 * 0.1

    def test_coil_read_for_run_status(self):
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client(coils=[True])

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_run_status"] is True

    def test_coil_false_when_stopped(self):
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client(coils=[False])

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_run_status"] is False

    def test_comms_ok_on_success(self):
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client()

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_comms_ok"] is True
        assert tags["vfd_comms_error"] == ""

    def test_batch_read_correct_address_range(self):
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client()

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            _run(reader.read_all_tags())

        # Should read from address 100, count=12 (100-111)
        client.read_holding_registers.assert_called_once_with(
            100, count=12, slave=1,
        )


# ---------------------------------------------------------------------------
# Test: Fault code lookup
# ---------------------------------------------------------------------------

class TestFaultCodeLookup:
    """Verify VFD fault codes map to correct descriptions."""

    def test_all_fault_codes_have_descriptions(self):
        for code in range(10):
            assert code in VFD_FAULTS

    def test_fault_code_zero_is_no_fault(self):
        assert VFD_FAULTS[0] == "No Fault"

    def test_fault_code_descriptions_in_tags(self):
        # Simulate fault code 4 = Overtemperature
        registers = [451, 500, 32, 2300, 3250, 1750, 650, 425, 185, 4, 100, 150]
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client(registers=registers)

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_fault_code"] == 4
        assert "Overtemperature" in tags["vfd_fault_description"]

    def test_unknown_fault_code(self):
        # Fault code 99 not in table
        registers = [451, 500, 32, 2300, 3250, 1750, 650, 425, 185, 99, 100, 150]
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client(registers=registers)

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_fault_code"] == 99
        assert "Unknown fault" in tags["vfd_fault_description"]


# ---------------------------------------------------------------------------
# Test: Calculated / derived tags
# ---------------------------------------------------------------------------

class TestCalculatedTags:
    """Verify derived tags are computed correctly."""

    def test_setpoint_vs_actual_hz(self):
        # setpoint=50.0 Hz, actual=45.1 Hz → gap = 4.9 Hz
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client()

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_setpoint_vs_actual_hz"] == 4.9

    def test_setpoint_vs_actual_zero_gap(self):
        # Both at 50.0 Hz
        registers = [500, 500, 32, 2300, 3250, 1750, 650, 425, 185, 0, 100, 150]
        reader = VFDReader(host="192.168.1.100")
        client = _make_mock_client(registers=registers)

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_setpoint_vs_actual_hz"] == 0.0


# ---------------------------------------------------------------------------
# Test: Connection failure — graceful degradation
# ---------------------------------------------------------------------------

class TestConnectionFailure:
    """Verify graceful degradation when VFD is unreachable."""

    def test_connection_refused_returns_zeroed(self):
        reader = VFDReader(host="192.168.1.100")

        client = mock.AsyncMock()
        client.connect = mock.AsyncMock(side_effect=ConnectionError("refused"))

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_comms_ok"] is False
        assert "refused" in tags["vfd_comms_error"]
        assert tags["vfd_output_hz"] == 0.0

    def test_register_read_error_returns_last_good(self):
        reader = VFDReader(host="192.168.1.100")

        # First read succeeds
        good_client = _make_mock_client()
        with mock.patch(
            _PATCH_TARGET,
            return_value=good_client,
        ):
            first = _run(reader.read_all_tags())

        assert first["vfd_comms_ok"] is True
        assert first["vfd_output_hz"] == 45.1

        # Second read fails — should return last good values
        bad_client = _make_mock_client(error=True)
        with mock.patch(
            _PATCH_TARGET,
            return_value=bad_client,
        ):
            second = _run(reader.read_all_tags())

        assert second["vfd_comms_ok"] is False
        assert second["vfd_output_hz"] == 45.1  # last known good

    def test_not_connected_returns_degraded(self):
        reader = VFDReader(host="192.168.1.100")

        client = _make_mock_client(connected=False)
        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            tags = _run(reader.read_all_tags())

        assert tags["vfd_comms_ok"] is False


# ---------------------------------------------------------------------------
# Test: Graceful no-host
# ---------------------------------------------------------------------------

class TestGracefulNoHost:
    """Verify reader works when no host is configured."""

    def test_empty_host_returns_zeroed_tags(self):
        reader = VFDReader(host="")
        tags = _run(reader.read_all_tags())

        assert tags["vfd_comms_ok"] is False
        assert tags["vfd_output_hz"] == 0.0
        assert tags["vfd_run_status"] is False
        assert tags["vfd_fault_description"] == "No Fault"

    def test_no_host_default(self):
        reader = VFDReader()
        tags = _run(reader.read_all_tags())

        assert tags["vfd_comms_ok"] is False
        assert len(tags) == 17  # All zeroed tags present


# ---------------------------------------------------------------------------
# Test: Register map override
# ---------------------------------------------------------------------------

class TestRegisterMapOverride:
    """Verify custom register map loading from JSON."""

    def test_load_custom_register_map(self):
        custom_map = {
            "vfd_output_hz": {"address": 200, "scale": 0.01, "type": "holding"},
            "vfd_run_status": {"address": 5, "scale": 1, "type": "coil"},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(custom_map, f)
            f.flush()

            loaded = _load_register_map(f.name)

        os.unlink(f.name)

        assert loaded["vfd_output_hz"]["address"] == 200
        assert loaded["vfd_output_hz"]["scale"] == 0.01
        assert loaded["vfd_run_status"]["address"] == 5

    def test_invalid_json_falls_back_to_default(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("NOT VALID JSON {{{")
            f.flush()

            loaded = _load_register_map(f.name)

        os.unlink(f.name)

        # Should fall back to default map
        assert loaded["vfd_output_hz"]["address"] == 100

    def test_nonexistent_path_uses_default(self):
        loaded = _load_register_map("/nonexistent/path/vfd_map.json")
        assert loaded == DEFAULT_REGISTER_MAP

    def test_reader_uses_custom_map(self):
        custom_map = {
            "vfd_output_hz": {"address": 200, "scale": 0.01, "type": "holding"},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(custom_map, f)
            f.flush()

            reader = VFDReader(
                host="192.168.1.100",
                register_map_path=f.name,
            )

        os.unlink(f.name)

        assert reader.register_map["vfd_output_hz"]["address"] == 200


# ---------------------------------------------------------------------------
# Test: Slave ID
# ---------------------------------------------------------------------------

class TestSlaveId:
    """Verify slave_id is passed through to Modbus calls."""

    def test_custom_slave_id(self):
        reader = VFDReader(host="192.168.1.100", slave_id=3)
        client = _make_mock_client()

        with mock.patch(
            _PATCH_TARGET,
            return_value=client,
        ):
            _run(reader.read_all_tags())

        client.read_holding_registers.assert_called_once_with(
            100, count=12, slave=3,
        )
        client.read_coils.assert_called_once_with(
            0, count=1, slave=3,
        )


# ---------------------------------------------------------------------------
# Test: Zeroed tags structure
# ---------------------------------------------------------------------------

class TestZeroedTags:
    """Verify the zeroed tag dict structure."""

    def test_zeroed_tags_has_all_expected_keys(self):
        tags = VFDReader._zeroed_tags()

        expected_keys = {
            "vfd_output_hz", "vfd_setpoint_hz", "vfd_output_amps",
            "vfd_output_volts", "vfd_dc_bus_volts", "vfd_motor_rpm",
            "vfd_torque_pct", "vfd_drive_temp_c", "vfd_power_kw",
            "vfd_fault_code", "vfd_accel_time_sec", "vfd_decel_time_sec",
            "vfd_run_status", "vfd_fault_description",
            "vfd_setpoint_vs_actual_hz", "vfd_comms_ok", "vfd_comms_error",
        }
        assert set(tags.keys()) == expected_keys

    def test_zeroed_tags_numeric_values_are_zero(self):
        tags = VFDReader._zeroed_tags()
        assert tags["vfd_output_hz"] == 0.0
        assert tags["vfd_motor_rpm"] == 0
        assert tags["vfd_fault_code"] == 0

    def test_zeroed_tags_comms_not_ok(self):
        tags = VFDReader._zeroed_tags()
        assert tags["vfd_comms_ok"] is False
        assert tags["vfd_run_status"] is False
