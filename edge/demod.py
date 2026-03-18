"""
RF·MESH Edge — Software Demodulator
=====================================
Pure-numpy implementations of AM, FM (NBFM/WBFM), USB, and LSB demodulation.

scipy.signal is used when available for better anti-aliasing filters before
decimation.  If scipy is not installed the code falls back to simple
integer decimation (reduced audio quality but still functional).

Typical usage
-------------
    from edge.demod import demodulate

    # iq_samples: complex64 numpy array from RSA306B IQ capture
    # sample_rate: IQ sample rate in Hz (e.g. 400_000 for 400 kHz span)

    pcm = demodulate(
        iq_samples,
        sample_rate=400_000,
        mode="FM",
        target_rate=16_000,
        max_deviation_hz=75_000,   # for WBFM; use 5_000 for NBFM voice
    )
    # pcm: int16 numpy array at 16 kHz

Demodulation modes
------------------
FM    Wide-band or narrow-band FM.  Angle discriminator on delayed conjugate.
AM    Amplitude modulation.  Envelope detection + DC removal.
USB   Upper sideband (SSB).  Hilbert-based phasing demodulation.
LSB   Lower sideband (SSB).  Same as USB with inverted sideband.
CW    Carrier Wave / Morse.  Same as USB but narrower (treat as FM with 0 deviation).
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

# ── Optional scipy import ─────────────────────────────────────────────────────

try:
    from scipy import signal as _signal
    _SCIPY = True
except ImportError:
    _SCIPY = False
    log.debug("scipy not available — using simple decimation (reduced audio quality)")


# ── Public API ────────────────────────────────────────────────────────────────

def demodulate(
    iq: np.ndarray,
    sample_rate: float,
    mode: str = "FM",
    target_rate: int = 16_000,
    *,
    max_deviation_hz: float = 75_000,
    ssb_bandwidth_hz: float = 3_000,
) -> np.ndarray:
    """
    Demodulate complex baseband IQ samples to PCM int16 audio.

    Parameters
    ----------
    iq:
        Complex64 IQ samples (baseband, centre frequency = 0 Hz).
    sample_rate:
        IQ sample rate in Hz.
    mode:
        Demodulation mode: ``"FM"``, ``"AM"``, ``"USB"``, ``"LSB"``, ``"CW"``
        (case-insensitive).
    target_rate:
        Output PCM sample rate in Hz (default 16 000).
    max_deviation_hz:
        Peak frequency deviation for FM (default 75 kHz for broadcast FM).
        Use ~5 000 Hz for NBFM voice channels.
    ssb_bandwidth_hz:
        SSB audio bandwidth in Hz for USB/LSB (default 3 kHz = voice).

    Returns
    -------
    np.ndarray
        int16 PCM samples at ``target_rate`` Hz, mono.
    """
    mode = mode.upper()
    iq = np.asarray(iq, dtype=np.complex64)

    if mode == "FM":
        audio = _demod_fm(iq, sample_rate, max_deviation_hz)
    elif mode == "AM":
        audio = _demod_am(iq, sample_rate)
    elif mode in ("USB", "LSB"):
        audio = _demod_ssb(iq, sample_rate, mode, ssb_bandwidth_hz)
    elif mode == "CW":
        # CW: treat as AM envelope with narrow bandwidth
        audio = _demod_am(iq, sample_rate)
    else:
        log.warning("Unknown demod mode %r — defaulting to FM", mode)
        audio = _demod_fm(iq, sample_rate, max_deviation_hz)

    # Decimate to target_rate
    decimate_ratio = int(round(sample_rate / target_rate))
    if decimate_ratio < 1:
        decimate_ratio = 1

    if decimate_ratio > 1:
        audio = _decimate(audio, decimate_ratio)

    # Normalize and convert to int16
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak

    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)


# ── Demodulation implementations ──────────────────────────────────────────────

def _demod_fm(iq: np.ndarray, sample_rate: float, max_deviation_hz: float) -> np.ndarray:
    """
    FM discriminator via delayed conjugate product.

    The instantaneous frequency is proportional to the angle of
    x[n] * conj(x[n-1]).  Dividing by 2π normalises to cycles/sample;
    multiplying by sample_rate gives Hz.
    """
    if len(iq) < 2:
        return np.zeros(1, dtype=np.float32)

    # Angle of delayed conjugate product → instantaneous frequency (Hz)
    inst_freq = np.angle(iq[1:] * np.conj(iq[:-1])) * (sample_rate / (2 * np.pi))

    # Normalise by max deviation
    if max_deviation_hz > 0:
        audio = inst_freq / max_deviation_hz
    else:
        audio = inst_freq

    return audio.astype(np.float32)


def _demod_am(iq: np.ndarray, sample_rate: float) -> np.ndarray:
    """AM envelope detection with DC removal."""
    envelope = np.abs(iq).astype(np.float32)

    # Remove DC component
    envelope -= np.mean(envelope)

    return envelope


def _demod_ssb(
    iq: np.ndarray,
    sample_rate: float,
    mode: str,
    bandwidth_hz: float,
) -> np.ndarray:
    """
    SSB demodulation using the phasing method.

    For USB: real part of IQ after low-pass filtering.
    For LSB: conjugate first (frequency-flip), then same as USB.
    """
    if mode == "LSB":
        iq = np.conj(iq)  # mirror spectrum for lower sideband

    # Low-pass filter to audio bandwidth, then take real part
    if _SCIPY:
        nyq = sample_rate / 2
        cutoff = min(bandwidth_hz / nyq, 0.99)
        b, a = _signal.butter(5, cutoff, btype="low")
        filtered = _signal.lfilter(b, a, iq)
        audio = np.real(filtered).astype(np.float32)
    else:
        # Without scipy: simple real-part extraction
        # Quality is lower but functional for voice
        audio = np.real(iq).astype(np.float32)

    return audio


# ── Decimation ────────────────────────────────────────────────────────────────

def _decimate(signal: np.ndarray, factor: int) -> np.ndarray:
    """
    Decimate signal by integer factor with anti-aliasing filter.

    Uses scipy.signal.decimate when available (FIR filter + decimation).
    Falls back to stride-based slicing (no pre-filtering) otherwise.
    """
    if _SCIPY:
        # scipy.signal.decimate handles factors > 13 by cascading
        max_single = 13
        remaining = factor
        out = signal.astype(np.float64)  # decimate works better in float64

        while remaining > 1:
            step = min(remaining, max_single)
            out = _signal.decimate(out, step, ftype="fir", zero_phase=True)
            remaining = remaining // step

        return out.astype(np.float32)
    else:
        return signal[::factor].astype(np.float32)


# ── Utility ───────────────────────────────────────────────────────────────────

def get_optimal_iq_sample_rate(target_audio_rate: int, mode: str = "FM") -> float:
    """
    Suggest a suitable IQ sample rate for the given demodulation mode.

    This is used when configuring the RSA306B IQ block capture bandwidth.
    The returned rate is chosen to allow clean decimation to target_audio_rate.

    Parameters
    ----------
    target_audio_rate: desired output audio sample rate (e.g. 16_000)
    mode:              demodulation mode

    Returns
    -------
    float: recommended IQ sample rate in Hz
    """
    mode = mode.upper()
    if mode == "FM":
        # Need to capture ≥ 2 × max_deviation + audio_bw
        # For broadcast WBFM: ~200 kHz; for NBFM voice: ~16 kHz
        # We use a multiple of target_audio_rate for clean decimation
        return target_audio_rate * 25   # e.g. 16 kHz × 25 = 400 kHz
    elif mode == "AM":
        return target_audio_rate * 8    # e.g. 16 kHz × 8 = 128 kHz
    elif mode in ("USB", "LSB", "CW"):
        return target_audio_rate * 4    # e.g. 16 kHz × 4 = 64 kHz
    else:
        return float(target_audio_rate * 10)
