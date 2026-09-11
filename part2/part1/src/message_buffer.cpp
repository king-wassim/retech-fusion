#include "../include/message_buffer.h"
#include <cstring>

MessageBuffer::MessageBuffer() : _head(0), _tail(0), _count(0) {}

void MessageBuffer::push(const char* payload, unsigned long capturedAt) {
    if (isFull()) {
        Serial.printf("[Buffer] Full (%d/%d) - oldest entry dropped\n", _count, BUFFER_MAX_SIZE);
        _tail = (_tail + 1) % BUFFER_MAX_SIZE;
        _count--;
    }

    strncpy(_buf[_head].payload, payload, PAYLOAD_MAX_LEN - 1);
    _buf[_head].payload[PAYLOAD_MAX_LEN - 1] = '\0';
    _buf[_head].capturedAt = capturedAt;

    _head = (_head + 1) % BUFFER_MAX_SIZE;
    _count++;

    Serial.printf("[Buffer] Stored reading (buffered: %d/%d, t=%lums)\n", _count, BUFFER_MAX_SIZE, capturedAt);
}

bool MessageBuffer::pop(BufferedMessage& out) {
    if (isEmpty()) {
        return false;
    }

    out = _buf[_tail];
    _tail = (_tail + 1) % BUFFER_MAX_SIZE;
    _count--;
    return true;
}
