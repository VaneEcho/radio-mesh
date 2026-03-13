"""
Spectrum device drivers for RF·MESH edge nodes.

Available drivers
-----------------
EM550Driver   R&S EM550 VHF/UHF Monitoring Receiver (20 MHz – 3.6 GHz, SCPI/TCP)
RSA306BDriver Tektronix RSA306B USB Analyzer (9 kHz – 6.2 GHz) — placeholder
MockDriver    Synthetic driver for development / CI (no hardware required)

Usage
-----
from edge.drivers import EM550Driver, MockDriver

with MockDriver() as rx:
    frame = rx.band_scan(20e6, 3600e6, step_hz=25_000, station_id="site-01")
"""
from .base import BaseSpectrumDriver, SpectrumFrame
from .em550 import EM550Driver
from .mock import MockDriver
from .rsa306b import RSA306BDriver

__all__ = [
    "BaseSpectrumDriver",
    "SpectrumFrame",
    "EM550Driver",
    "MockDriver",
    "RSA306BDriver",
]
