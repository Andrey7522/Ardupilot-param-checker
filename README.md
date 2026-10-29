# 📡🐝 ArduPilot Parameter Checker

A utility for quickly checking the configuration of ArduPilot-based drones (Plane, Copter, QuadPlane) before takeoff. The script identifies critical errors that could prevent the drone from taking off or crashing, as well as suspicious settings that could impact safety.

---

> *Note:* The architecture and check rules were developed based on a real prototype based on the Cube flight controller (ArduPilot QuadPlane firmware). The code was written using an AI assistant to speed up routine tasks, while all check logic, testing, and validation were performed independently.

## 🚀 Features

- **Automatic device type detection**: the script automatically determines whether it is a Plane, Copter, or QuadPlane based on an analysis of the parameter dump. - **Deep Analysis**: Checks Arming, Failsafe, battery, EKF, Fence, motors, RC, and vibration settings.
- **Report Generation**: Creates a <filename>_REPORT.txt file with a detailed explanation of each error.
- **Parameter Marking**: Creates a <filename>_CHECKED.param file, with markers such as `!!!` (critical), `!` (warning), or `i` (info) to the left of problematic lines. Conveniently open in Notepad.
- **HTML Support**: The `--html` flag generates a colorized report for viewing in a browser.

## 🛠 Installation and Run (from Source)

1. Make sure you have Python 3.8+ installed. 

2. Clone the repository:
```bash
git clone https://github.com/Andrey7522/Ardupilot-param-checker.git
cd Ardupilot-param-checker

## 📦 Building EXE for Windows

1. Install PyInstaller:

pip install pyinstaller

2. Building EXE

pyinstaller --onefile check_params.py

3. The finished file will appear in the dist/check_params.exe folder.

# Example of using an EXE:
cmd
check_params.exe "C:\Users\andre\Desktop\Work\Params.param"

## 📸 Example of work


## 👨‍💻 Author: Andrey Chebotarev
