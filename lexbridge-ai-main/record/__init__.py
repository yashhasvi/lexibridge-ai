"""
Record module: capture audio from the system microphone and save to file.
"""

from record.recorder import Recorder, list_devices, record_to_file

__all__ = [
    "Recorder",
    "list_devices",
    "record_to_file",
]
