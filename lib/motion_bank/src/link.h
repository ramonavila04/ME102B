// Board-to-board link between the main board (HUZZAH32: UI, scale, schedule) and the
// motion board (Feather ESP32 V2: six modules). Byte-oriented framing over a UART:
//
//   0xA5 | len | type | seq | payload[len] | crc8
//
// crc8 is CRC-8/ATM (poly 0x07, init 0) over len, type, seq and the payload. The parser
// resynchronises on the next 0xA5 after any bad frame. Hardware-independent; unit-tested
// on the host (pio test -e native).
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace link {

constexpr uint8_t kStart = 0xA5;
constexpr uint8_t kMaxPayload = 16;
constexpr size_t kMaxFrame = 4 + kMaxPayload + 1;

// Main -> motion
enum MsgType : uint8_t {
  kPing = 0x01,        // no payload
  kHome = 0x02,        // [module]          home one module (0..5)
  kDispense = 0x03,    // [module]          dispense one pill from a module
  kAbort = 0x04,       // no payload        stop any motion, back to idle
  kClearFault = 0x05,  // no payload
  // Motion -> main
  kAck = 0x81,     // [accepted]            seq = the command's seq
  kResult = 0x82,  // [module, outcome, beams, steps, jams]   seq = the command's seq
  kStatus = 0x83,  // [state, module, homedMask, fault]       sent on change and on ping
};

uint8_t crc8(const uint8_t* data, size_t n);

// Writes a frame into `out` (at least kMaxFrame bytes); returns its length (0 if the
// payload is too long).
size_t encode(uint8_t type, uint8_t seq, const uint8_t* payload, uint8_t len, uint8_t* out);

struct Frame {
  uint8_t type = 0, seq = 0, len = 0;
  uint8_t payload[kMaxPayload] = {};
};

class Parser {
 public:
  // Feed one received byte. Returns true when a complete, valid frame is ready in frame().
  bool feed(uint8_t b);
  const Frame& frame() const { return frame_; }
  uint32_t crcErrors() const { return crcErrors_; }
  uint32_t lengthErrors() const { return lengthErrors_; }

 private:
  enum class St : uint8_t { Start, Len, Type, Seq, Payload, Crc } st_ = St::Start;
  Frame frame_, work_;
  uint8_t idx_ = 0;
  uint32_t crcErrors_ = 0, lengthErrors_ = 0;
};

}  // namespace link
