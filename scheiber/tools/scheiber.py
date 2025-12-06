"""
Scheiber CAN bus control library.

Provides low-level functions for sending commands to Scheiber devices over CAN bus.
"""

import time
import sys
import logging
import can

# Module logger
logger = logging.getLogger(__name__)


def parse_hex_data(hex_string):
    """Convert hex string (e.g., '01 53 E8 86 83') to bytes."""
    return bytes.fromhex(hex_string.replace(" ", ""))


def bloc9_switch(can_interface, bloc9_id, switch_nr, state, brightness=None):
    """
    Send a Bloc9 switch command via CAN bus with optional brightness control.

    Args:
        can_interface: CAN interface name (e.g., "can1")
        bloc9_id: Bloc9 device ID (number)
        switch_nr: Switch number (0-5 for S1-S6)
        state: Boolean state (True for ON, False for OFF)
        brightness: Optional brightness level (0-255). If provided:
            - 0: Turn off (same as state=False)
            - 1-254: Set brightness level (byte 1 = 0x11, byte 3 = brightness)
            - 255: Turn on (byte 1 = 0x01)
            - If None: Simple ON/OFF command (byte 1 = 0x01/0x00)

    Constructs CAN ID as follows:
    - Shift bloc9_id left by 3 bits
    - Set the most significant bit to 1
    - Use that byte as the lowest byte in 0x02360600

    Constructs 4-byte body:
    - Without brightness: [switch_nr, 0x01/0x00, 0x00, 0x00]
    - With brightness 1-254: [switch_nr, 0x11, 0x00, brightness]
    - Special case brightness=0: [switch_nr, 0x00, 0x00, 0x00] (turn off)
    - Special case brightness=255: [switch_nr, 0x01, 0x00, 0x00] (turn on)

    Example: bloc9_id=10, switch_nr=3, state=True -> CAN ID: 0x023606D0, Data: 03 01 00 00
    Example: bloc9_id=10, switch_nr=3, brightness=128 -> CAN ID: 0x023606D0, Data: 03 11 00 80
    """
    bus = None
    try:
        # Open CAN bus
        bus = can.interface.Bus(channel=can_interface, interface="socketcan")

        # Construct CAN ID: lowest byte = (bloc9_id << 3) | 0x80, masked to ensure it's a single byte
        low_byte = ((bloc9_id << 3) | 0x80) & 0xFF
        can_id = 0x02360600 | low_byte

        # Construct 4-byte body based on brightness parameter
        if brightness is not None:
            # Brightness control mode (0-255 direct value)
            if brightness == 0:
                # Brightness 0 = turn off
                data = bytes([switch_nr, 0x00, 0x00, 0x00])
                logger.debug(
                    f"Bloc9 ID:{bloc9_id} Switch:{switch_nr} -> OFF (brightness=0)"
                )
            elif brightness == 255:
                # Brightness 255 = turn on (without brightness control)
                data = bytes([switch_nr, 0x01, 0x00, 0x00])
                logger.debug(
                    f"Bloc9 ID:{bloc9_id} Switch:{switch_nr} -> ON (brightness=255)"
                )
            else:
                # Set brightness level (byte 1 = 0x11, byte 3 = brightness)
                # Clamp to valid range 1-254
                brightness_byte = max(1, min(254, brightness))
                data = bytes([switch_nr, 0x11, 0x00, brightness_byte])
                logger.debug(
                    f"Bloc9 ID:{bloc9_id} Switch:{switch_nr} -> brightness={brightness_byte} (0x{brightness_byte:02X})"
                )
        else:
            # Simple ON/OFF mode
            state_byte = 0x01 if state else 0x00
            data = bytes([switch_nr, state_byte, 0x00, 0x00])
            logger.debug(
                f"Bloc9 ID:{bloc9_id} Switch:{switch_nr} -> {'ON' if state else 'OFF'}"
            )

        # Send the message
        msg = can.Message(arbitration_id=can_id, data=data)
        bus.send(msg)
        logger.info(
            f"CAN TX: ID=0x{can_id:08X} Data={' '.join(f'{b:02X}' for b in data)}"
        )
    except Exception as e:
        logger.error(f"Failed to send CAN message: {e}")
        raise
    finally:
        # Ensure the bus is properly closed
        if bus:
            bus.shutdown()


def send_burst(bus, sender_id, data, repetitions=3, interval=0.033):
    """
    Send CAN data in burst repetitions to simulate a high-priority CAN message.

    Args:
        bus: CAN bus instance
        sender_id: CAN sender ID (e.g., "04001A80")
        data: Hex data string (e.g., "01 53 E8 86 83")
        repetitions: Number of times to send the data (default 3)
        interval: Time in seconds between repetitions (default 33ms)
    """
    arbitration_id = int(sender_id, 16)
    payload = parse_hex_data(data)

    logger.debug(
        f"Sending burst: ID=0x{sender_id} repetitions={repetitions} interval={interval}s"
    )

    for i in range(repetitions):
        msg = can.Message(arbitration_id=arbitration_id, data=payload)
        bus.send(msg)
        logger.info(f"CAN TX burst {i+1}/{repetitions}: ID=0x{sender_id} Data={data}")
        if i < repetitions - 1:
            time.sleep(interval)


def _setup_logging():
    """Setup logging for command-line usage."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )


if __name__ == "__main__":
    _setup_logging()

    # Parse command line arguments
    switch_nr = sys.argv[1] if len(sys.argv) > 1 else "3"
    bus_nr = sys.argv[2] if len(sys.argv) > 2 else "7"
    state_arg = sys.argv[3] if len(sys.argv) > 3 else "ON"

    state = state_arg.upper() != "OFF"

    logger.info(
        f"Command: Bloc9 ID:{bus_nr} Switch:{switch_nr} -> {'ON' if state else 'OFF'}"
    )

    try:
        bloc9_switch("can1", int(bus_nr), int(switch_nr), state)
        logger.info("Command sent successfully")
    except Exception as e:
        logger.error(f"Command failed: {e}")
        sys.exit(1)
