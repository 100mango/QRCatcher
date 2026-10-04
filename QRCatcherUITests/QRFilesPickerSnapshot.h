#ifndef QR_FILES_PICKER_SNAPSHOT_H
#define QR_FILES_PICKER_SNAPSHOT_H
#include <math.h>
#include <stddef.h>
#include <string.h>

#define QR_FILES_SNAPSHOT_MAX_NODES 2048
typedef enum { QRFilesOther, QRFilesWindow, QRFilesNavigationBar, QRFilesButton, QRFilesUnknown } QRFilesKind;
typedef struct { double x, y, width, height; } QRFilesFrame;
typedef struct {
    int parent;
    QRFilesKind kind;
    const char *identifier;
    const char *label;
    int enabled;
    QRFilesFrame frame;
} QRFilesNode;

static inline int QRFilesName(const char *value, const char *expected) {
    return value && strcmp(value, expected) == 0;
}
static inline int QRFilesUsableFrame(QRFilesFrame f) {
    return isfinite(f.x) && isfinite(f.y) && isfinite(f.width) && isfinite(f.height) &&
        isfinite(f.x + f.width) && isfinite(f.y + f.height) && f.width > 0 && f.height > 0;
}
static inline int QRFilesContains(QRFilesFrame outer, QRFilesFrame inner) {
    return QRFilesUsableFrame(outer) && QRFilesUsableFrame(inner) && inner.x >= outer.x && inner.y >= outer.y &&
        inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}
static inline int QRFilesDescendant(const QRFilesNode *nodes, int child, int ancestor) {
    for (int parent = nodes[child].parent; parent >= 0; parent = nodes[parent].parent)
        if (parent == ancestor) return 1;
    return 0;
}
static inline int QRFilesPickerPresentationReady(const QRFilesNode *nodes, size_t count) {
    if (!nodes || count == 0 || count > QR_FILES_SNAPSHOT_MAX_NODES || nodes[0].parent != -1) return 0;
    // Flattening must preserve a finite tree, never an unknown/cyclic graph.
    for (size_t i = 1; i < count; i++) if (nodes[i].parent < 0 || nodes[i].parent >= (int)i) return 0;
    int picker = -1, bar = -1, cancel = -1, window = -1;
    for (size_t i = 0; i < count; i++) {
        if (nodes[i].kind == QRFilesOther && QRFilesName(nodes[i].identifier, "Browse View (Picker)")) {
            if (picker >= 0) return 0;
            picker = (int)i;
        }
    }
    if (picker < 0) return 0;
    for (int parent = nodes[picker].parent; parent >= 0; parent = nodes[parent].parent) {
        if (nodes[parent].kind == QRFilesWindow) { window = parent; break; }
    }
    if (window < 0 || !QRFilesContains(nodes[window].frame, nodes[picker].frame)) return 0;
    for (size_t i = 0; i < count; i++) {
        if (nodes[i].kind == QRFilesNavigationBar &&
            QRFilesName(nodes[i].identifier, "FullDocumentManagerViewControllerNavigationBar") &&
            QRFilesDescendant(nodes, (int)i, picker)) {
            if (bar >= 0) return 0;
            bar = (int)i;
        }
    }
    if (bar < 0 || !QRFilesContains(nodes[picker].frame, nodes[bar].frame)) return 0;
    for (size_t i = 0; i < count; i++) {
        if (nodes[i].kind == QRFilesButton && QRFilesName(nodes[i].label, "Cancel") &&
            QRFilesDescendant(nodes, (int)i, bar)) {
            if (cancel >= 0) return 0;
            cancel = (int)i;
        }
    }
    return cancel >= 0 && nodes[cancel].enabled && QRFilesContains(nodes[bar].frame, nodes[cancel].frame);
}
#endif
