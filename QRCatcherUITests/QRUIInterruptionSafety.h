#import <XCTest/XCTest.h>
#include <stdio.h>
#include <stdlib.h>

// UI-test code only. A failure assertion can unwind an interruption handler and
// leave XCTest's default handler free to press a permission button. Never return
// or throw on this path: stop only this disposable test runner, without UI input.
__attribute__((noreturn)) static inline void QRStopForUnexpectedInterruption(XCUIElement *alert) {
    fprintf(stderr, "QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION\n");
    fflush(stderr);
    (void)alert; // No AX query/assertion may throw before the non-returning stop.
    abort();
}

static inline id QRInstallFailClosedInterruptionMonitor(XCTestCase *testCase) {
    return [testCase addUIInterruptionMonitorWithDescription:@"Stop before every unexpected system interruption" handler:^BOOL(XCUIElement *alert) {
        QRStopForUnexpectedInterruption(alert);
    }];
}

static inline void QRRespondToObservedCameraPrompt(XCUIElement *alert, NSString *action) {
    // Exact title and buttons observed on iOS 27 in run 37151432147, SE3 and
    // Pro Max. An unfamiliar OS/localization must fail without guessing.
    @try {
        NSString *title = @"Allow “QRCatcher” to access your camera?";
        XCUIApplication *system = [[XCUIApplication alloc] initWithBundleIdentifier:@"com.apple.springboard"];
        if (![alert.label isEqualToString:title] || !system.alerts[title].exists ||
            !([action isEqualToString:@"Allow"] || [action isEqualToString:@"Don’t Allow"])) {
            QRStopForUnexpectedInterruption(alert);
        }
        XCUIElementQuery *actions = [alert.buttons matchingPredicate:[NSPredicate predicateWithFormat:@"label == %@", action]];
        if (actions.count != 1 || !actions.firstMatch.enabled || !actions.firstMatch.hittable) {
            QRStopForUnexpectedInterruption(alert);
        }
        NSLog(@"QRCATCHER_EXPECTED_CAMERA_ACTION:%@ TITLE:%@", action, title);
        [actions.firstMatch tap];
    } @catch (NSException *exception) {
        (void)exception;
        QRStopForUnexpectedInterruption(alert);
    }
}
