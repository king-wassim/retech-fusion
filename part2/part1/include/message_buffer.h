#ifndef MESSAGE_BUFFER_H
#define MESSAGE_BUFFER_H

#include <Arduino.h>
#include "config.h"

struct BufferedMessage {
    char payload[PAYLOAD_MAX_LEN];
    unsigned long capturedAt;
};

class MessageBuffer {
public:
    MessageBuffer();

    void push(const char* payload, unsigned long capturedAt);
    bool pop(BufferedMessage& out);

    bool isEmpty() const { return _count == 0; }
    bool isFull() const { return _count >= BUFFER_MAX_SIZE; }
    int count() const { return _count; }

private:
    BufferedMessage _buf[BUFFER_MAX_SIZE];
    int _head = 0;
    int _tail = 0;
    int _count = 0;
};

#endif
