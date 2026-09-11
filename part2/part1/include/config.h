#ifndef CONFIG_H
#define CONFIG_H

// Wi-Fi configuration
#define WIFI_SSID "Galaxy S20 Fe"
#define WIFI_PASSWORD "s20fe2004"

// MQTT configuration
#define MQTT_SERVER "192.168.20.15"
#define MQTT_PORT 1883
#define MQTT_CLIENT_ID "ESP32_SENSOR_DEVICE"
#define MQTT_TOPIC_SENSORS "esp32/sensors"

// Sensor pins
#define DHT22_PIN 4
#define FLAME_DIGITAL_PIN 5
#define FLAME_ANALOG_PIN 34

// Timing configuration (ms)
#define SENSOR_READ_INTERVAL 5000
#define MQTT_RECONNECT_INTERVAL 5000

// MQTT liveness
#define MQTT_KEEPALIVE 4
#define MQTT_SOCKET_TIMEOUT 2

// Offline buffer
#define BUFFER_MAX_SIZE 20
#define PAYLOAD_MAX_LEN 512

// Validation ranges
#define TEMP_MIN -40.0f
#define TEMP_MAX 80.0f
#define HUMIDITY_MIN 0.0f
#define HUMIDITY_MAX 100.0f
#define FLAME_ANALOG_MIN 0
#define FLAME_ANALOG_MAX 4095

#endif
