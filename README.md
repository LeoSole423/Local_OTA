# Local_OTA - WiFi Remote Logger for ESP32

This project demonstrates how to redirect all `ESP_LOG` output from an ESP32 device to a remote client over a WiFi network. It's a useful tool for debugging and monitoring your device without a physical serial connection.

The application connects to a configured WiFi network and starts a TCP server. When a client connects to the server, all subsequent log messages are sent to the client.

## Features

-   Connects an ESP32 to a WiFi network.
-   Starts a TCP server to listen for incoming connections.
-   Redirects all `ESP_LOG` output to a connected TCP client.
-   Securely manages WiFi credentials using the project configuration system (`menuconfig`).
-   Clean and modular code structure.

## How to Use

### Step 1: Configure Your WiFi Credentials

**This is a critical step.** You must provide your WiFi network's SSID and password to the project. This is done safely through the ESP-IDF configuration menu, so your credentials are not hardcoded in the source code.

1.  Open a terminal in the project's root directory.
2.  Run the configuration menu:
    ```bash
    idf.py menuconfig
    ```
3.  Navigate to `Example Configuration`.
4.  Set the `WiFi SSID` to your network's name.
5.  Set the `WiFi Password` to your network's password.
6.  Save the configuration and exit.

### Step 2: Build and Flash the Project

1.  Connect your ESP32 board to your computer.
2.  Build and flash the project using the ESP-IDF command:
    ```bash
    idf.py flash
    ```

### Step 3: Monitor the Output

You can monitor the output in two ways:

#### A. Serial Monitor (to get the IP address)

First, use the serial monitor to see the initial logs and find out the IP address assigned to your ESP32.

1.  Run the serial monitor:
    ```bash
    idf.py monitor
    ```
2.  Look for a message similar to this:
    ```
    I (wifi_station): got ip:192.168.1.123
    ```
3.  Take note of the IP address. You can now close the serial monitor by pressing `Ctrl+]`.

#### B. Remote Logging via TCP

Once you have the IP address, you can connect from any computer on the same network to receive the logs.

1.  Use a tool like `netcat` (`nc`) or `telnet`. The server runs on port `3333`.
2.  In your computer's terminal, run the following command, replacing `<ESP32_IP_ADDRESS>` with the address you noted earlier:
    ```bash
    nc <ESP32_IP_ADDRESS> 3333
    ```
    Or with telnet:
    ```bash
    telnet <ESP32_IP_ADDRESS> 3333
    ```

You should now see the log messages from your ESP32 appearing in your terminal.

## Project Structure

-   `main/main.c`: The main application entry point. It initializes the logger and runs the main task.
-   `main/wifi_logger.c`: Contains all the logic for WiFi connection and the TCP logging server.
-   `main/wifi_logger.h`: Header file for the `wifi_logger` component.
-   `main/Kconfig.projbuild`: Defines the configuration options for `menuconfig`.
