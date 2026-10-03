#include "QRPortableDecoder.h"
#include "ReadBarcode.h"
#include "Barcode.h"
#include "ReaderOptions.h"
#include <exception>

int QRPortableDecodeGray(const uint8_t *pixels, size_t byteCount, uint32_t width,
                         uint32_t height, QRPortablePayloadCallback callback, void *context)
{
    if (!pixels || !callback || width == 0 || height == 0 || width > 1536 || height > 1536 ||
        uint64_t(width) * height != byteCount)
        return -1;
    try {
        auto options = ZXing::ReaderOptions().formats(ZXing::BarcodeFormat::QRCode)
            .textMode(ZXing::TextMode::Plain).maxNumberOfSymbols(33);
        auto results = ZXing::ReadBarcodes(ZXing::ImageView(pixels, int(width), int(height), ZXing::ImageFormat::Lum), options);
        // Observe one beyond our budget so a dense image is rejected instead
        // of silently returning a truncated set of QR payloads.
        if (results.size() > 32) return -3;
        for (const auto& result : results) {
            if (!result.isValid()) continue;
            const auto text = result.text();
            if (text.size() > 16384) return -3;
            if (!text.empty() && callback(reinterpret_cast<const uint8_t*>(text.data()), text.size(), context)) return -4;
        }
        return 0;
    } catch (const std::exception&) { return -2; }
}
