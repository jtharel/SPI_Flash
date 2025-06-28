#this aids in acquring the serial number used in the spi_flash.py script here. Will also confirm your SOIC clip is attached properly and can be used to extract the flash contents.

from pyftdi.ftdi import Ftdi

def list_ftdi_devices():
    """Lists connected FTDI devices and prints their serial numbers."""
    print("Searching for FTDI devices...")
    for device_info in Ftdi.list_devices():
        # device_info is a tuple: (url, description, serial_number)
        url, description, serial_number = device_info
        print(f"  URL: {url}, Description: {description}, Serial: {serial_number}")

if __name__ == "__main__":
    list_ftdi_devices()
