/*
* Copyright 2019 Nu-book Inc.
* Copyright 2023 Axel Waggershauser
*/
// SPDX-License-Identifier: Apache-2.0

#pragma once

#define ZXING_READERS
// disabled ZXING_WRITERS

#define ZXING_ENABLE_1D 0
#define ZXING_ENABLE_AZTEC 0
#define ZXING_ENABLE_DATAMATRIX 0
#define ZXING_ENABLE_MAXICODE 0
#define ZXING_ENABLE_PDF417 0
#define ZXING_ENABLE_QRCODE 1

// disabled ZXING_EXPERIMENTAL_API
// disabled ZXING_USE_ZINT

// Version numbering
#define ZXING_VERSION_MAJOR 3
#define ZXING_VERSION_MINOR 1
#define ZXING_VERSION_PATCH 1
#define ZXING_VERSION_SUFFIX ""

#define ZXING_VERSION_STR "3.1.1"
