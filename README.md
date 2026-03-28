# Duet Night Abyss Game Script

This project is a Windows desktop automation tool for Duet Night Abyss.

## Environment Requirements

- OS: Windows 10 or Windows 11
- Python: 3.11+ (3.12 recommended)
- Display scaling: 100% recommended for template-based detection

## Dependencies

This project uses a few external Python packages:

- `opencv-python`
- `numpy`
- `mss`

## Quick Setup

1. Clone or download this repository.
2. Open PowerShell in the project root.
3. Create and activate a virtual environment.
4. Install dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install opencv-python numpy mss
```

If PowerShell blocks activation, run this once in the same terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Run

```powershell
python main.py
```

## Notes

- The project stores runtime files in [data](data).
- Static templates and route definitions are under [dna/definitions](dna/definitions).
- The app is Windows-specific because input and window handling are implemented in [dna/platform/windows.py](dna/platform/windows.py).

