#Dump SPI Flash chip using SOIC clip.

import sys
import os
import time
from pyftdi.ftdi import Ftdi
from pyftdi.spi import SpiController

# --- Configuration ---
# Replace 'FT1K78SG' with the actual serial number of your FTDI device.
# You found this using the previous Python script.
FTDI_SERIAL_NUMBER = 'FT1K78SG' 

# The chip name you identified. This is for display purposes in the script.
FLASH_CHIP_NAME = 'cFeon QH128A / EN25QH128'

# Output file for the flash dump
OUTPUT_FILENAME = 'flash_dump.bin'

# SPI Clock Frequency (Hz)
# You might need to adjust this. Start lower if you have stability issues.
# 1MHz (1_000_000), 5MHz (5_000_000), 10MHz (10_000_000) are common.
# FT232H/FT4232H can go up to 30MHz (or 60MHz in certain modes).
SPI_FREQ_HZ = 5_000_000

# --- SPI Flash Commands (Common JEDEC SPI NOR Flash) ---
CMD_READ_JEDEC_ID = 0x9F  # Read JEDEC ID
CMD_READ_DATA = 0x03      # Read Data (Slow)
CMD_FAST_READ_DATA = 0x0B # Fast Read Data (requires 1 dummy byte)
CMD_READ_STATUS_REGISTER_1 = 0x05 # Read Status Register-1

# --- Chip Specifics (from cFeon QH128A datasheet) ---
# Manufacturer ID, Memory Type, Capacity from JEDEC ID (0x9F)
# cFeon (Eon Silicon Solution Inc.) Manufacturer ID: 0x1C
# QH128A (128Mbit): Memory Type: 0x70, Capacity: 0x18
EXPECTED_JEDEC_ID = (0x1C, 0x70, 0x18)
FLASH_SIZE_BYTES = 16 * 1024 * 1024  # 128 Megabit = 16 MByte

# --- FTDI Device Initialization ---
def initialize_ftdi(serial_number):
    """Initializes the FTDI controller and returns a SPI port object."""
    spi = SpiController()
    try:
        # Use the serial number to specifically target your device
        # The '/1' specifies the first channel (Channel A)
        ftdi_url = f'ftdi://::{serial_number}/1' 
        print(f"Attempting to open FTDI device at {ftdi_url}...")
        spi.configure(ftdi_url)
        
        # Get the first SPI port (corresponds to Channel A)
        port = spi.get_port(0)
        port.set_frequency(SPI_FREQ_HZ)
        
        # Set SPI Mode (CPOL, CPHA). Mode 0 (CPOL=0, CPHA=0) is typical for SPI flash.
        # pyftdi's SpiPort uses set_mode(mode) where mode = (cpol << 1) | cpha
        port.set_mode(0) # Sets CPOL=0, CPHA=0

        print(f"FTDI device configured for SPI at {SPI_FREQ_HZ / 1_000_000} MHz (Mode 0).")
        return spi, port
    except Exception as e:
        print(f"Error initializing FTDI device: {e}")
        # Add a note about potential causes if initialization fails
        if "unable to open" in str(e).lower() or "device not found" in str(e).lower():
            print("This often means another process (like the ftdi_sio kernel module) has claimed the device, or permissions are incorrect.")
            print("Ensure 'ftdi_sio' is blacklisted/unloaded and you have necessary USB device permissions (e.g., using sudo or udev rules).")
        return None, None

# --- SPI Flash Operations ---
def read_jedec_id(spi_port):
    """Reads the JEDEC ID from the flash chip."""
    print("Reading JEDEC ID (0x9F)...")
    try:
        # Send JEDEC ID command (0x9F) and read 3 bytes
        jedec_id = spi_port.exchange([CMD_READ_JEDEC_ID], readlen=3)
        print(f"Raw JEDEC ID: {jedec_id.hex()}")
        
        # Parse the JEDEC ID
        manufacturer_id = jedec_id[0]
        memory_type = jedec_id[1]
        capacity = jedec_id[2]
        
        print(f"Manufacturer ID: 0x{manufacturer_id:02X}")
        print(f"Memory Type:     0x{memory_type:02X}")
        print(f"Capacity:        0x{capacity:02X}")

        if (manufacturer_id, memory_type, capacity) == EXPECTED_JEDEC_ID:
            print(f"JEDEC ID matches expected for {FLASH_CHIP_NAME}.")
        else:
            print(f"WARNING: JEDEC ID does NOT match expected ID for {FLASH_CHIP_NAME}.")
            print(f"Expected: {hex(EXPECTED_JEDEC_ID[0])}, {hex(EXPECTED_JEDEC_ID[1])}, {hex(EXPECTED_JEDEC_ID[2])}")
        return True
    except Exception as e:
        print(f"Error reading JEDEC ID: {e}")
        print("Please check your SPI wiring (CLK, CS, MOSI, MISO, VCC, GND) and ensure WP#/HOLD# are pulled high if not used.")
        return False

def read_flash_chip(spi_port, size, output_file):
    """Reads the entire flash chip into a binary file."""
    print(f"Reading {size / (1024*1024):.2f} MBytes from {FLASH_CHIP_NAME} to {output_file}...")
    
    # Use CMD_FAST_READ_DATA (0x0B) for faster reading
    # It requires an address (3 bytes) and a dummy byte
    
    # Prepare the header for each read block: command + 3-byte address + 1 dummy byte
    # We will read in chunks to manage memory and transfer size.
    CHUNK_SIZE = 4096 # Read in 4KB chunks
    
    bytes_read = 0
    start_time = time.time()

    with open(output_file, 'wb') as f:
        while bytes_read < size:
            # Calculate address bytes
            address_bytes = [(bytes_read >> 16) & 0xFF,
                             (bytes_read >> 8) & 0xFF,
                             bytes_read & 0xFF]
            
            # Prepare command buffer: FAST_READ_CMD + Address + Dummy Byte
            command_buffer = [CMD_FAST_READ_DATA] + address_bytes + [0x00] # 0x00 is the dummy byte
            
            # Determine how many bytes to read in this chunk
            bytes_to_read_this_chunk = min(CHUNK_SIZE, size - bytes_read)
            
            try:
                # Perform the SPI transfer
                data = spi_port.exchange(command_buffer, readlen=bytes_to_read_this_chunk)
                f.write(data)
                bytes_read += len(data)

                # Print progress
                if bytes_read % (CHUNK_SIZE * 10) == 0: # Update every 40KB
                    progress_percent = (bytes_read / size) * 100
                    sys.stdout.write(f"\rProgress: {progress_percent:.2f}% ({bytes_read}/{size} bytes)")
                    sys.stdout.flush()

            except Exception as e:
                print(f"\nError reading flash at offset 0x{bytes_read:X}: {e}")
                print("Read operation aborted.")
                return False
    
    end_time = time.time()
    read_duration = end_time - start_time
    read_speed = (size / (1024 * 1024)) / read_duration # MB/s
    
    sys.stdout.write(f"\rProgress: 100.00% ({bytes_read}/{size} bytes)\n")
    print(f"Flash read complete in {read_duration:.2f} seconds ({read_speed:.2f} MB/s).")
    print(f"Output saved to {output_file}")
    return True

# --- Main Execution ---
if __name__ == '__main__':
    print("--- FTDI SPI Flash Utility ---")
    print(f"Attempting to connect to FTDI device with serial: {FTDI_SERIAL_NUMBER}")

    controller, spi_port = initialize_ftdi(FTDI_SERIAL_NUMBER)

    if spi_port:
        try:
            print("\n--- Testing Flash Chip ---")
            if read_jedec_id(spi_port):
                print("\n--- Starting Full Chip Read ---")
                read_flash_chip(spi_port, FLASH_SIZE_BYTES, OUTPUT_FILENAME)
            else:
                print("Failed to read JEDEC ID. Aborting full chip read.")
        finally:
            print("\nClosing FTDI connection...")
            controller.close()
    else:
        print("FTDI device initialization failed. Cannot proceed.")
