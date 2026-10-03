#ifndef QR_PORTABLE_DECODER_H
#define QR_PORTABLE_DECODER_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Callback bytes are valid only for this call; nonzero requests an early return.
typedef int (*QRPortablePayloadCallback)(const uint8_t *, size_t, void *);
// 0 completed (possibly no QR), -1 invalid bounds, -2 decoder/allocation error,
// -3 payload limit, -4 callback cancellation. Never opens links or writes history.
int QRPortableDecodeGray(const uint8_t *pixels, size_t byteCount, uint32_t width,
                         uint32_t height, QRPortablePayloadCallback callback, void *context);
#ifdef __cplusplus
}
#endif
#endif
