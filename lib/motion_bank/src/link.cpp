#include "link.h"

#include <string.h>

namespace link {

uint8_t crc8(const uint8_t* data, size_t n) {
  uint8_t c = 0;
  for (size_t i = 0; i < n; ++i) {
    c ^= data[i];
    for (int b = 0; b < 8; ++b) c = (c & 0x80) ? static_cast<uint8_t>((c << 1) ^ 0x07) : static_cast<uint8_t>(c << 1);
  }
  return c;
}

size_t encode(uint8_t type, uint8_t seq, const uint8_t* payload, uint8_t len, uint8_t* out) {
  if (len > kMaxPayload) return 0;
  out[0] = kStart;
  out[1] = len;
  out[2] = type;
  out[3] = seq;
  if (len) memcpy(out + 4, payload, len);
  out[4 + len] = crc8(out + 1, 3 + len);
  return 5 + len;
}

bool Parser::feed(uint8_t b) {
  switch (st_) {
    case St::Start:
      if (b == kStart) st_ = St::Len;
      return false;
    case St::Len:
      if (b > kMaxPayload) {
        ++lengthErrors_;
        st_ = (b == kStart) ? St::Len : St::Start;
        return false;
      }
      work_.len = b;
      st_ = St::Type;
      return false;
    case St::Type:
      work_.type = b;
      st_ = St::Seq;
      return false;
    case St::Seq:
      work_.seq = b;
      idx_ = 0;
      st_ = work_.len ? St::Payload : St::Crc;
      return false;
    case St::Payload:
      work_.payload[idx_++] = b;
      if (idx_ >= work_.len) st_ = St::Crc;
      return false;
    case St::Crc: {
      uint8_t buf[3 + kMaxPayload];
      buf[0] = work_.len;
      buf[1] = work_.type;
      buf[2] = work_.seq;
      memcpy(buf + 3, work_.payload, work_.len);
      st_ = St::Start;
      if (crc8(buf, 3 + work_.len) != b) {
        ++crcErrors_;
        return false;
      }
      frame_ = work_;
      return true;
    }
  }
  return false;
}

}  // namespace link
