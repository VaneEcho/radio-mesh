"""
Spectrum device drivers for RF·MESH edge nodes.

Available drivers
-----------------
EM550Driver   R&S EM550 VHF/UHF Monitoring Receiver (20 MHz – 3.6 GHz, SCPI/TCP)
RSA306BDriver Tektronix RSA306B USB Analyzer (9 kHz – 6.2 GHz) — placeholder

Usage
-----
from edge.drivers import EM550Driver

with EM550Driver(host="192.168.1.100") as rx:
    frame = rx.scan_range(88e6, 108e6, step_hz=25_000, station_id="site-01")
"""
from .base import BaseSpectrumDriver, SpectrumFrame
from .em550 import EM550Driver
from .rsa306b import RSA306BDriver

__all__ = [
    "BaseSpectrumDriver",
    "SpectrumFrame",
    "EM550Driver",
    "RSA306BDriver",
]
