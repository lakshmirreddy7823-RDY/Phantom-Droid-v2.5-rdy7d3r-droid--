# Phantom-Droid-v2.5-rdy7d3r-droid--

# Phantom-Droid v2.5

**Android (ADB) + iOS (usbmuxd)**

Created by **@Rdy7d3r**

## Overview

Phantom-Droid v2.5 is a Python-based device diagnostics utility for checking Android and iOS devices connected to your computer.

It provides a terminal-based interface for authorized device inspection and connection checks.

## Features

- Android device detection through ADB
- iOS device detection through usbmuxd
- Connected-device information
- Device connection status
- Android version information (where available)
- iOS device information (where available)
- Separate Android and iOS menus
- Combined device overview
- Simple terminal interface

## Requirements

- Python 3.10 or newer
- Android Debug Bridge (ADB)
- usbmuxd
- libimobiledevice tools for iOS support

## Installation

Clone the repository:

```bash
git clone  https://github.com/lakshmirreddy7823-RDY/Phantom-Droid-v2.5-rdy7d3r-droid-- 
cd Phantom-Droid-v2.5-rdy7d3r-droid-- 
```

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Install system tools on Kali/Debian:

```bash
sudo apt update
sudo apt install adb usbmuxd libimobiledevice-utils
```

## Usage

Run the program:

```bash
python3 phantom-droid-v2.5.py
```

### Main Menu

```text
[a]    Android Menu
[i]    iOS Menu
[both] Show All Devices
[99]   Exit
```

## Important Notes

- Only inspect devices you own or have permission to manage.
- Android debugging must be enabled and authorized.
- iOS device access may require device pairing and trust confirmation.
- Available information depends on the device and operating system.
- This project is intended for diagnostics, not bypassing device security or extracting private information.

## Author

**@Rdy7d3r**

## License

MIT License — see the `LICENSE` file.
