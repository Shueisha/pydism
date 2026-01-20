# pydism

A simple Windows repair tool using DISM and SFC.

![Windows](https://img.shields.io/badge/Windows-10%2F11-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Python](https://img.shields.io/badge/Python-3.x-yellow)

## What It Does

- **Scan Health** - Checks Windows for corruption (no changes made)
- **Restore Health** - Scans and repairs corruption using Windows Update
- **System File Checker** - Verifies and repairs protected system files
- **Full Repair** - Runs both DISM and SFC in sequence

## Download

Grab the latest `pydism.exe` from [Releases](../../releases).

## Usage

1. Download `pydism.exe`
2. **Right-click** → **Run as Administrator**
3. Select an option from the menu
4. Wait for completion

## The 62.3% "Pause"

During Restore Health, DISM often appears to freeze at 62.3%. **This is normal.** 

DISM is analyzing the component store, which can take 10-20 minutes. pydism explains this while it's happening so you know it's not stuck.

## Building From Source

```powershell
# Requires Python 3.x and PyInstaller
pip install pyinstaller
pyinstaller --onefile --name pydism pydism.py
```

The executable will be in the `dist/` folder.

## Requirements

- Windows 10 or Windows 11
- Administrator privileges
- Internet connection (for Restore Health to download components)

## How It Works

pydism is a wrapper around Windows' built-in repair tools:

- **DISM** (Deployment Image Servicing and Management) - Repairs the Windows component store
- **SFC** (System File Checker) - Repairs protected system files

These are the same commands IT professionals run manually:
```cmd
DISM /Online /Cleanup-Image /RestoreHealth
sfc /scannow
```

pydism adds:
- Smart progress indicators
- Explanation of the 62.3% pause behavior
- Clean progress bars
- Logging for troubleshooting

## License

MIT License - see [LICENSE](LICENSE) for details.
