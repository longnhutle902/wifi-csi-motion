# Wi-Fi CSI Indoor Motion Detection

[Tiếng Việt](README.md) · English

A first-year undergraduate project detecting **motion / no detected motion**
in an indoor environment using two ESP32-S3 N16R8 boards.
ESP-NOW connects the transmitter and receiver directly; no external router is required.
The receiver streams CSI to a **Python host**, which performs signal processing,
calibration, and motion decisions. This is not a deployed on-device classifier.

## Hardware and processing

- 2.4 GHz, channel 11, HT20, target transmission rate 50 packets/s.
- 52 useful L-LTF subcarriers from a 64-bin CSI buffer.
- Hampel amplitude cleaning, offset log amplitude, per-packet mean removal,
  6 Hz low-pass filtering, and a robust sliding variation score.
- A calibrated pair of thresholds and consecutive confirmations stabilize motion decisions.
- A 100 Hz interpolation grid is used internally; this does not increase the physical sample rate.

The current code does **not** implement the 0.3 Hz high-pass filter or per-packet
median removal described in earlier handoff material. The existing DSP was retained
to preserve the experimental algorithm. See [code review](reports/CODE_REVIEW.md).

## Install and run

Python 3.11 is recommended.

```sh
python -m venv .venv
# Activate .venv using the command for your shell, then:
python -m pip install -r requirements.txt
python host/web_dashboard.py
python host/record.py --help
python host/evaluate.py --out reports/review_validation
python -m unittest discover -s tests -v
```

The dashboard is served at `http://127.0.0.1:8050` in English by default.
Use `?lang=vi` for Vietnamese or `?lang=en` for English.
Use `--http-host 0.0.0.0` only when LAN access is intended.
Windows batch launchers reference the original local tools directory;
the Python commands above are portable.

Firmware builds use ESP-IDF 5.3.2, target `esp32s3`:

```sh
cd firmware/csi_tx  # or firmware/csi_rx
idf.py build
```

Do not flash both boards as the same role. The current checked-in configuration
targets 50 Hz transmission and 921600 baud for UART/monitor output.

## Experimental evidence and limits

The repository includes 121,647 raw CSI packets from six indoor sessions and
the original experiment reports. Earlier reports recorded detection in 26/26
walking events. These are results for the measured scenarios, not a general
accuracy guarantee. The evaluation code was subsequently corrected to count
false-positive tails spanning a motion-to-static transition. Consult
[revalidation notes](reports/REVALIDATION_20261110.md) before citing historical metrics.

WiFall checks 464 activity files from ten subjects. All files exceeded a reference
peak-score threshold in revalidation. This is **activity-file threshold coverage**;
it is not a binary-classification accuracy estimate and provides no matched
static false-alarm assessment. The current saved calibration differs from the
historical reference; subject counts are also unequal.

The receiver queue-drop counter does not establish zero over-the-air packet loss.
Fan interference was evaluated only in the recorded setup. No live hardware
retest or reflashing is implied by software regression tests.

## Layout

| Path | Purpose |
|---|---|
| `firmware/csi_tx`, `firmware/csi_rx` | ESP32-S3 radio acquisition |
| `host/wifisense` | CSI parsing, DSP, detector, replay engine |
| `host/web_dashboard.py` | Live and replay web dashboard |
| `host/record.py` | Guided experiment recording |
| `host/evaluate.py` | Indoor-session metrics and reports |
| `host/wifall_check.py` | External activity-file threshold check |
| `data/sessions` | Original indoor recordings |
| `reports` | Historical results and review notes |
| `tests` | Regression tests; also run in GitHub Actions |

External raw datasets and local build artifacts are excluded from Git.
