"""
Tektronix RSA306B USB Spectrum Analyzer — Driver (placeholder)
==============================================================
TODO: implement using tekrsa-api-wrap + libRSA_API.so

Hardware limits:
  Frequency range : 9 kHz – 6.2 GHz
  Max real-time BW: 40 MHz per acquisition
  Interface       : USB 3.0
  Library         : tekrsa-api-wrap (pip install tekrsa-api-wrap)
  Reference       : https://github.com/NTIA/tekrsa-api-wrap

The scan_range() implementation follows the same pattern as EM550:
  - segment the requested range into ≤40 MHz chunks
  - iterate, stitch, return a single SpectrumFrame
"""
from __future__ import annotations

from .base import BaseSpectrumDriver, SpectrumFrame


class RSA306BDriver(BaseSpectrumDriver):
    """Placeholder — not yet implemented."""

    FREQ_MIN_HZ: float = 9e3
    FREQ_MAX_HZ: float = 6_200e6
    MAX_REALTIME_BW_HZ: float = 40e6

    @property
    def freq_min_hz(self) -> float:
        return self.FREQ_MIN_HZ

    @property
    def freq_max_hz(self) -> float:
        return self.FREQ_MAX_HZ

    @property
    def max_span_per_segment_hz(self) -> float:
        return self.MAX_REALTIME_BW_HZ

    def connect(self) -> None:
        raise NotImplementedError("RSA306B driver not yet implemented")

    def disconnect(self) -> None:
        pass

    def scan_range(self, start_hz, stop_hz, step_hz=None,
                   station_id="", task_id="") -> SpectrumFrame:
        raise NotImplementedError("RSA306B driver not yet implemented")
