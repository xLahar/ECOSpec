# Serial communication for ESP32 servo control
# Run: python piCommsTest.py

def send_servo_command(ser):
    """Send command '1' to ESP32 to initiate servo movement"""
    try:
        ser.write(b'1\r\n')
        print("Command sent to ESP32 - Initiating servo movement")
        
        # Wait for response from ESP32
        response = ser.readline().decode('utf-8').strip()
        if response:
            print(f"ESP32 response: {response}")
        else:
            print("No response received from ESP32")
            
    except Exception as e:
        print(f"Error in communication: {e}")