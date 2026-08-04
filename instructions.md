# Running Instructions: Ledger Pro

## 1. Development Mode (Running from Source)
To run the application directly using your Python interpreter:

```bash
python3 /Users/yashaswee/ledger/gui.py
```

## 2. Building the Standalone Application
To package the tool into a double-clickable `.app` (Mac) or `.exe` (Windows):

### For macOS:
```bash
python3 -m PyInstaller --windowed --onefile --noconsole --name "LedgerPro" \
--hidden-import pandas --hidden-import openpyxl gui.py
```

### For Windows:
```bash
python3 -m PyInstaller --windowed --onefile --name "LedgerPro" \
--hidden-import pandas --hidden-import openpyxl gui.py
```

## 3. Troubleshooting

### "zsh: command not found: pyinstaller"
If the `pyinstaller` command is not recognized, it means the binary is not in your PATH. Always use the Python module prefix:
`python3 -m PyInstaller ...`

### "ModuleNotFoundError: No module named 'bs4' or 'pandas'"
Ensure all dependencies are installed in your environment:
```bash
python3 -m pip install beautifulsoup4 pandas openpyxl pyinstaller
```

### Application "quit unexpectedly" on Mac
This can happen if you are running an older version of macOS. Try building without the `--onefile` flag for better compatibility:
```bash
python3 -m PyInstaller --windowed --noconsole --name "LedgerPro" gui.py
```

### "Permission Denied" when opening .app
Right-click the `LedgerPro.app` in your `dist/` folder and select **Open**. This bypasses the macOS unsigned developer warning.
