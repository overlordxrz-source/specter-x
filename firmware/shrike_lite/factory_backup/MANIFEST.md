# Factory Shrike Lite backup manifest

The physical board was backed up before any file modification. The binary
backup is local and gitignored under:

`runs/shrike_lite_factory_backup_20261024/`

| File | Size | SHA-256 |
|---|---:|---|
| `main.py` | 463 B | `0e3b259a4f2387260823435a3a53e98dbc9f4164860cff95d84421a2f73f5b59` |
| `blink_all.bin` | 45 KiB | `cd40b215efa40f272fe788202417d7f312a4e8f772fb06c2f96beafaf4fb65fd` |

The `blink_all.bin` hash matches the manufacturer's
`test/bitstreams/v1_4/blink_all.bin` and `test/multi_hardware_test/blink_all.bin`
at `vicharak-in/shrike` commit `2186d6b`.

No factory file was modified, erased or replaced. The factory `main.py` was
restored by soft reset after the transient RP2040 heartbeat.
