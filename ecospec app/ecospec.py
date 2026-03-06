#!/usr/bin/env python3
"""
ECOSpec — Raspberry Pi 5 Native App Launcher
"""

import webview
import os
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'app', 'index.html')


class EcoSpecAPI:

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def detect_hardware(self):
        """
        Check which hardware is physically connected.
        Returns a dict of component states for the status panel.
        """
        result = {}

        #  ESP32 MCU
        # Checks common USB serial ports the ESP32 shows up as
        esp32_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
        if esp32_ports:
            result['esp32'] = {'status': 'ONLINE', 'cls': 'ok', 'detail': esp32_ports[0]}
        else:
            result['esp32'] = {'status': 'NOT FOUND', 'cls': 'warn', 'detail': None}

        # ACUROS CQD Camera
        import subprocess
        camera_found = False
        camera_device = None
        try:
            output = subprocess.check_output(
                ['v4l2-ctl', '--list-devices'],
                stderr=subprocess.DEVNULL
            ).decode()

            # Split into blocks per device
            blocks = output.strip().split('\n\n')
            for block in blocks:
                lines = block.strip().splitlines()
                if not lines:
                    continue
                name = lines[0].lower()
                # Skip Pi built-in devices
                if any(skip in name for skip in ['bcm2835', 'vc4', 'hdmi', 'codec', 'isp']):
                    continue
                # Find the /dev/video line for this block
                for line in lines[1:]:
                    dev = line.strip()
                    if dev.startswith('/dev/video'):
                        camera_found = True
                        camera_device = dev
                        break
                if camera_found:
                    break
        except Exception:
            pass

        if camera_found:
            result['camera'] = {'status': 'LINKED', 'cls': 'ok', 'detail': camera_device}
        else:
            result['camera'] = {'status': 'NOT FOUND', 'cls': 'warn', 'detail': None}

            def save_csv(self, csv_text, full_path):
                """Write csv_text to full_path. Creates directories if needed."""
                try:
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
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

    api.set_window(window)

    webview.start(
        debug=False,
        gui='gtk',
        http_server=False,
    )


if __name__ == '__main__':
    main()
