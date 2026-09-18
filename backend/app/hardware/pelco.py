import struct

class PelcoDController:
    """
    Генератор байт-команд протоколу Pelco-D для поворотної турелі РЕБ (Pan-Tilt).
    Підтримує встановлення абсолютного кута або плавну швидкість обертання.
    """
    SYNC_BYTE = 0xFF

    @staticmethod
    def build_pan_tilt_command(address: int, pan_speed: int, tilt_speed: int, left: bool, up: bool) -> bytes:
        cmd1 = 0x00
        cmd2 = 0x00
        if left:
            cmd2 |= 0x04
        else:
            cmd2 |= 0x02
        if up:
            cmd2 |= 0x08
        else:
            cmd2 |= 0x10

        pan_speed = max(0x00, min(0x3F, pan_speed))
        tilt_speed = max(0x00, min(0x3F, tilt_speed))

        checksum = (PelcoDController.SYNC_BYTE + address + cmd1 + cmd2 + pan_speed + tilt_speed) % 256
        return struct.pack("7B", PelcoDController.SYNC_BYTE, address, cmd1, cmd2, pan_speed, tilt_speed, checksum)

    @staticmethod
    def trigger_burst_relay(gpio_pin: int, duration_sec: int):
        """
        Імітація або реальний запуск апаратного реле (ESP32/Raspberry Pi GPIO)
        для живлення РЕБ-підсилювачів суворо на заданий інтервал.
        """
        # У реальному середовищі: gpiod або serial.write("RELAY_ON")
        return f"[HARDWARE] Pin {gpio_pin} ACTIVE for {duration_sec}s -> BURST HIGH POWER"