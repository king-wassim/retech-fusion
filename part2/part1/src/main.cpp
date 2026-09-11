#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"
#include "sensor_manager.h"
#include "message_buffer.h"
#include "sensors/dht22_sensor.h"
#include "sensors/flame_sensor.h"

WiFiClient espClient;
PubSubClient mqttClient(espClient);
SensorManager sensorManager;
MessageBuffer messageBuffer;

unsigned long lastSensorRead = 0;
unsigned long lastMqttReconnectAttempt = 0;

bool wasMqttConnected = false;
bool wasWifiConnected = false;
volatile bool wifiAssociated = false;

void onWifiEvent(WiFiEvent_t event) {
    switch (event) {
        case ARDUINO_EVENT_WIFI_STA_GOT_IP:
            wifiAssociated = true;
            Serial.printf("\n[WiFi Event] Got IP: %s\n", WiFi.localIP().toString().c_str());
            break;
        case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
            if (wifiAssociated) {
                Serial.println("\n[WiFi Event] *** STA DISCONNECTED ***");
            }
            wifiAssociated = false;
            break;
        default:
            break;
    }
}

void setupWiFi();
void setupMQTT();
void reconnectMQTT();
void publishSensorData();
void flushBuffer();

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("\n\n=== ESP32 IoT Sensor Device ===");
    Serial.println("Starting initialization...\n");

    WiFi.onEvent(onWifiEvent);
    setupWiFi();
    setupMQTT();

    Serial.println("[Main] Registering sensors...");
    sensorManager.addSensor(new DHT22Sensor(DHT22_PIN));
    sensorManager.addSensor(new FlameSensor(FLAME_DIGITAL_PIN, FLAME_ANALOG_PIN));

    if (!sensorManager.initAll()) {
        Serial.println("[Main] Warning: Not all sensors initialized successfully");
    }

    Serial.println("[Main] Setup complete! Starting main loop.\n");
}

void loop() {
    bool wifiUp = wifiAssociated && (WiFi.status() == WL_CONNECTED);
    if (!wifiUp && wasWifiConnected) {
        Serial.println("\n[WiFi] *** CONNECTION LOST *** - readings will be buffered");
        if (mqttClient.connected()) {
            mqttClient.disconnect();
        }
    }
    wasWifiConnected = wifiUp;

    if (!wifiUp) {
        Serial.println("[Main] WiFi disconnected, reconnecting...");
        setupWiFi();
    }

    if (mqttClient.connected() && !espClient.connected()) {
        Serial.println("\n[MQTT] TCP socket dead - forcing PubSubClient disconnect");
        mqttClient.disconnect();
    }

    bool mqttUp = mqttClient.connected();
    if (!mqttUp && wasMqttConnected) {
        Serial.printf("\n[MQTT] *** CONNECTION LOST *** (rc=%d) - readings will be buffered\n", mqttClient.state());
    }
    wasMqttConnected = mqttUp;

    if (!mqttUp) {
        reconnectMQTT();
    }

    mqttClient.loop();

    unsigned long now = millis();
    if (now - lastSensorRead >= SENSOR_READ_INTERVAL) {
        lastSensorRead = now;
        publishSensorData();
    }

    delay(100);
}

void setupWiFi() {
    Serial.printf("\n[WiFi] Connecting to %s", WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 40) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println(" SUCCESS");
        Serial.printf("[WiFi] IP address: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[WiFi] RSSI: %d dBm\n", WiFi.RSSI());
    } else {
        Serial.println(" FAILED");
        Serial.println("[WiFi] Check SSID, password, and WiFi signal strength");
    }
}

void setupMQTT() {
    mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
    mqttClient.setKeepAlive(MQTT_KEEPALIVE);
    mqttClient.setSocketTimeout(MQTT_SOCKET_TIMEOUT);
    Serial.printf("[MQTT] Broker: %s:%d\n", MQTT_SERVER, MQTT_PORT);
    Serial.printf("[MQTT] Client ID: %s, keepalive: %ds\n", MQTT_CLIENT_ID, MQTT_KEEPALIVE);
}

void reconnectMQTT() {
    unsigned long now = millis();
    if (now - lastMqttReconnectAttempt < MQTT_RECONNECT_INTERVAL) {
        return;
    }

    lastMqttReconnectAttempt = now;

    if (!mqttClient.connected()) {
        Serial.print("[MQTT] Attempting connection... ");
        if (mqttClient.connect(MQTT_CLIENT_ID)) {
            Serial.println("CONNECTED");
            Serial.printf("[MQTT] *** CONNECTION RESTORED *** Topic: %s\n", MQTT_TOPIC_SENSORS);
            wasMqttConnected = true;
            flushBuffer();
        } else {
            Serial.printf("FAILED (rc=%d)\n", mqttClient.state());
            Serial.println("[MQTT] Will retry in 5 seconds");
        }
    }
}

void publishSensorData() {
    JsonDocument jsonDoc;

    if (!sensorManager.readAll(jsonDoc)) {
        Serial.println("[Publish] Warning: Some sensor reads failed");
    }

    char jsonBuffer[PAYLOAD_MAX_LEN];
    unsigned long capturedAt = jsonDoc["timestamp"].as<unsigned long>();
    size_t jsonSize = serializeJson(jsonDoc, jsonBuffer, sizeof(jsonBuffer));

    if (!wifiAssociated || WiFi.status() != WL_CONNECTED || !espClient.connected() || !mqttClient.connected()) {
        Serial.println("[Publish] OFFLINE - buffering reading for later replay");
        messageBuffer.push(jsonBuffer, capturedAt);
        return;
    }

    if (mqttClient.publish(MQTT_TOPIC_SENSORS, jsonBuffer)) {
        Serial.printf("[Publish] SUCCESS - %zu bytes sent\n", jsonSize);
        Serial.printf("  Topic: %s\n", MQTT_TOPIC_SENSORS);
        Serial.printf("  Payload: %s\n", jsonBuffer);
    } else {
        Serial.printf("[Publish] FAILED (rc=%d) - buffering reading for later replay\n", mqttClient.state());
        messageBuffer.push(jsonBuffer, capturedAt);
    }
}

void flushBuffer() {
    if (messageBuffer.isEmpty()) {
        return;
    }

    Serial.printf("[Buffer] Flushing %d buffered reading(s)...\n", messageBuffer.count());

    BufferedMessage msg;
    int flushed = 0;
    while (messageBuffer.pop(msg)) {
        if (mqttClient.publish(MQTT_TOPIC_SENSORS, msg.payload)) {
            flushed++;
            Serial.printf("[Backup] SUCCESS - replayed reading t=%lums (%d left)\n", msg.capturedAt, messageBuffer.count());
            Serial.printf("  Topic: %s\n", MQTT_TOPIC_SENSORS);
            Serial.printf("  Payload: %s\n", msg.payload);
        } else {
            messageBuffer.push(msg.payload, msg.capturedAt);
            Serial.printf("[Buffer] Publish failed mid-flush, %d reading(s) re-queued\n", messageBuffer.count());
            break;
        }
        mqttClient.loop();
    }

    Serial.printf("[Buffer] Flush complete - %d sent, %d remaining\n", flushed, messageBuffer.count());
}
