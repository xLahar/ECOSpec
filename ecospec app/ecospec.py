#!/usr/bin/env python3
"""
ECOSpec — Raspberry Pi 5 Native App Launcher
PyWebView native window with Python API for CSV export.
"""

import webview
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'app', 'index.html')


class EcoSpecAPI:
    """
    Exposed to JS as window.pywebview.api
    Called from JS: await window.pywebview.api.save_csv(csvText, fullPath)
    """

    def save_csv(self, csv_text, full_path):
        """
        Write csv_text to full_path on disk.
        Creates the directory if it doesn't exist.
        Returns { ok: True, path: "..." } or { ok: False, error: "..." }
        """
        try:
            # Ensure the directory exists (e.g. Documents folder may not exist)
            directory = os.path.dirname(full_path)
            os.makedirs(directory, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(csv_text)

            return {'ok': True, 'path': full_path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


def main():
    api = EcoSpecAPI()

    window = webview.create_window(
        title='ECOSpec',
        url=f'file://{HTML_PATH}',
        width=1024,
        height=600,
        resizable=False,
        fullscreen=False,
        frameless=False,
        min_size=(1024, 600),
        background_color='#0a0e14',
        text_select=False,
        confirm_close=False,
        on_top=False,
        js_api=api,
    )

    webview.start(
        debug=False,
        gui='gtk',
        http_server=False,
    )


if __name__ == '__main__':
    main()
