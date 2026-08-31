"""Versioned database migrations."""

from . import (
    b1_0001,
    b3_0002,
    b4_0003,
    b5_0004,
    b7_0005,
    b8_0006,
    b9_0007,
    b11_0008,
    b12_0009,
    b12_0010,
    b13_0011,
    b14_0012,
    b15_0013,
)

MIGRATIONS = (
    b1_0001,
    b3_0002,
    b4_0003,
    b5_0004,
    b7_0005,
    b8_0006,
    b9_0007,
    b11_0008,
    b12_0009,
    b12_0010,
    b13_0011,
    b14_0012,
    b15_0013,
)
LATEST_REVISION = MIGRATIONS[-1].REVISION
CURRENT_TABLES = (*b1_0001.TABLES, *b7_0005.TABLES)

__all__ = ["CURRENT_TABLES", "LATEST_REVISION", "MIGRATIONS"]
