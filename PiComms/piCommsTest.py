# Serial communication for ESP32 servo control
# Run: python piCommsTest.py

import serial
from time import sleep

# Initialize serial connection
try:
    ser = serial.Serial("/dev/ttyS0", 115200, timeout=2)
    print("Serial connection established on /dev/ttyS0 at 115200 baud")
except serial.SerialException as e:
    print(f"Error opening serial port: {e}")
    exit(1)

def send_servo_command():
    """Send command '1' to ESP32 to initiate servo movement"""
    try:
        ser.write(b'1\r\n')
        print("Command '1' sent to ESP32 - Initiating servo movement")
        
        # Wait for response from ESP32
        response = ser.readline().decode('utf-8').strip()
        if response:
            print(f"ESP32 response: {response}")
        else:
            print("No response received from ESP32")
            
    except Exception as e:
        print(f"Error in communication: {e}")

def main():
    print("ESP32 Servo Control Interface")
    print("Commands:")
    print("  1 - Move servo")
    print("  q - Quit")
    print("-" * 30)
    
    try:
        while True:
            user_input = input("Enter command: ").strip().lower()
            
            if user_input == '1':
                send_servo_command()
            elif user_input == 'q':
                print("Exiting...")
                break
            else:
                print("Invalid command. Use '1' for servo control or 'q' to quit.")
                
            sleep(0.1)  # Small delay between commands
            
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
    finally:
        ser.close()
        print("Serial connection closed")

if __name__ == "__main__":
    main()