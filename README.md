# Manga & Comic Tray Translator

A lightweight desktop screen-snipping OCR and translation utility built with Python, PyQt5, and EasyOCR, designed for reading manga and comics with a background System Tray interface.

## Features
- **System Tray Resident:** Runs quietly in the system tray with quick settings and a clean **Exit** option.
- **Screen Snipping via Drag:** Hold `Alt` + left-click drag over text bubbles to select a region and trigger translation.
- **Manga-Focused OCR:** Uses `EasyOCR` for text extraction across comic/manga panels (`en` or `ja` + `en`).
- **Translation Tone Options:** Choose between **Manga Casual** (colloquial/natural flow for dialogue), **Literary**, or **Direct**.
- **Font & Copy Controls:** Customize font family and size (including quick `A+` / `A-` controls on the popup) and one-click **Copy** for translated text.

## Requirements
- Python 3.10+ (tested with PyQt5, EasyOCR, NumPy, Pillow, and `deep-translator`)
- Internet connection for translation backends

## Installation
```bash
pip install PyQt5 easyocr pillow numpy deep-translator keyboard
```

## Usage
Run the script from your terminal:

```bash
python manga_translator.py
```

1. Wait until `EasyOCR آماده است.` appears and the **M** icon appears in the system tray.
2. Hold **Alt** and drag the left mouse button around a manga/comic speech bubble or text box.
3. Click **ترجمه متن داخل کادر** to view the original text and Persian translation.
4. Use **📋 کپی ترجمه** to copy the translation or right-click the tray icon to open settings or exit.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.