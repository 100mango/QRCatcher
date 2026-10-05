#!/usr/bin/env python3
"""Closed portable metadata contract. This does not compile or execute AppKit."""
import hashlib
import json
import math
import re
import uuid

CASES = {
    'testNativeWindowResizeKeepsFullActionTitles': ['mac-before-resize', 'mac-minimum-window'],
    'testChineseCriticalFlow': ['mac-chinese-reopened', 'mac-chinese-policy'],
}
PRIVACY_ZH = 'Celluloid、QRCatcher 和 TouchColor 在设备本地处理照片、相机画面、二维码或颜色数据，开发者不收集或上传这些数据。用户主动分享、打开链接，以及系统 iCloud 同步等行为由相应服务处理。如有隐私问题，请联系 100mango@gmail.com。本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。'
ATTRIBUTES = {'accessibilityFont', 'font', 'accessibilityForegroundColor', 'foregroundColor', 'accessibilityBackgroundColor', 'backgroundColor'}
PATH_IDENTIFIERS = {'mac.windowContent', 'mac.pane.result', 'mac.pane.history', 'mac.sheet.privacy', 'mac.payload', 'mac.status', 'privacy.offlineBody', 'unidentified'}
ISSUES = {'depth-limit', 'cycle', 'node-limit', 'unsupported-public-node', 'outside-root-or-unknown-owner', 'missing-content', 'missing-attached-sheet', 'unexpected-sheet-state', 'window-order-limit', 'invalid-window-frame', 'screen-identity-unknown'}
REASONS = {'missing-target', 'duplicate-target', 'node-limit', 'missing-or-duplicate-rendered-child', 'incomplete-public-traversal', 'wrong-value-or-frame', 'unsupported-or-mismatched-attributed-string', 'invalid-attribute-range', 'run-limit', 'public-attributed-string', 'partial-public-attributed-string'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer(value, minimum=0, maximum=None):
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def utf16(value):
    return len(value.encode('utf-16-le')) // 2


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_uuid(value):
    try:
        return type(value) is str and str(uuid.UUID(value)).upper() == value
    except (ValueError, TypeError, AttributeError):
        return False


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'Unknown or missing keys')


def decode(data, limit=32768):
    require(type(data) is bytes and 0 < len(data) <= limit, 'Oversized or absent receipt')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid JSON') from error


def request_binding(value, token, case, checkpoint, sequence, request_id):
    require(canonical_uuid(token) and canonical_uuid(request_id), 'Invalid expected UUID')
    require(case in CASES and checkpoint in CASES[case], 'Wrong selected case/checkpoint')
    require(integer(sequence, 1, 6) and sequence == CASES[case].index(checkpoint) + 1, 'Wrong sequence')
    for key, expected in [('token', token), ('case', case), ('checkpoint', checkpoint), ('requestID', request_id)]:
        require(type(value.get(key)) is str and value[key] == expected, 'Stale or wrong '+key)
    require(type(value.get('schema')) is int and value['schema'] == 1, 'Wrong schema')
    require(type(value.get('sequence')) is int and value['sequence'] == sequence, 'Wrong sequence type/value')


def validate_request(data, *, token, case, checkpoint, sequence, request_id, started, now, consumed_ids=(), consumed_checkpoints=(), requests=0):
    value = decode(data, 1024)
    exact(value, ['schema', 'token', 'case', 'checkpoint', 'sequence', 'requestID', 'uptime'])
    request_binding(value, token, case, checkpoint, sequence, request_id)
    require(integer(requests, 0, 5) and sequence == requests + 1, 'Request limit/order')
    require(request_id not in consumed_ids and checkpoint not in consumed_checkpoints, 'Duplicate request/checkpoint')
    require(number(started) and number(now) and number(value['uptime']) and started <= value['uptime'] <= now and now-value['uptime'] <= 5, 'Stale request')
    return value


def target_specs(case, checkpoint):
    chinese = case == 'testChineseCriticalFlow'
    rows = [
        ('fixed-unicode-payload' if chinese else 'fixed-url-payload', 'mac.payload', 'mac.pane.result', 'QRCatcher 你好 🌈 123' if chinese else 'https://example.com/qrcatcher?source=golden', False),
        ('fixed-status', 'mac.status', 'mac.pane.result', '已保存在本机' if chinese else 'Result copied', False),
        ('fixed-link-policy', '', 'mac.pane.result', '只有点击「在浏览器中打开」才会打开链接。' if chinese else 'Links open only when you choose Open in Browser.', False),
        ('fixed-saved-count', '', 'mac.pane.history', '本机已保存 1 条记录' if chinese else '1 saved on this Mac', False),
    ]
    if checkpoint == 'mac-chinese-policy':
        rows.append(('fixed-privacy-policy', 'privacy.offlineBody', 'mac.sheet.privacy', PRIVACY_ZH, True))
    return rows


def frame(value, nullable=False):
    if nullable and value is None:
        return
    require(type(value) is list and len(value) == 4 and all(number(v) for v in value) and value[2] >= 0 and value[3] >= 0, 'Invalid frame')


def contained(outer, inner):
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[0]+inner[2] <= outer[0]+outer[2] and inner[1]+inner[3] <= outer[1]+outer[3]


def window(value, nullable=False):
    if nullable and value is None:
        return
    exact(value, ['number', 'frame', 'visible', 'key', 'main', 'sheetParent', 'attachedSheet'])
    require(integer(value['number'], -1) and integer(value['sheetParent'], -1) and integer(value['attachedSheet'], -1), 'Invalid window identity')
    require(all(type(value[k]) is bool for k in ['visible', 'key', 'main']), 'Invalid window state')
    frame(value['frame'], nullable=True)


def node(value, *, expected, pane, root, owning_window, observed):
    exact(value, ['role', 'root', 'window', 'path', 'frame', 'enabled', 'valueUTF16Length', 'valueSHA256'])
    require(type(value['role']) is str and re.fullmatch(r'AX[A-Za-z0-9]{1,62}', value['role']) is not None, 'Invalid public role')
    require(value['root'] == root and type(value['window']) is int and value['window'] == owning_window['number'], 'Outside-root node')
    path = value['path']
    require(type(path) is list and 1 <= len(path) <= 17 and all(type(v) is str and v in PATH_IDENTIFIERS for v in path) and pane in path, 'Wrong/missing pane path')
    require(type(value['enabled']) is bool and integer(value['valueUTF16Length'], -1, 4096), 'Invalid value metadata')
    require(value['valueSHA256'] == 'unknown' if value['valueUTF16Length'] == -1 else type(value['valueSHA256']) is str and re.fullmatch(r'[0-9a-f]{64}', value['valueSHA256']) is not None, 'Invalid value hash')
    frame(value['frame'], nullable=not observed)
    if observed:
        require(value['frame'][2] > 0 and value['frame'][3] > 0 and owning_window['frame'] is not None and contained(owning_window['frame'], value['frame']), 'Outside-window target geometry')
        require(value['valueUTF16Length'] == utf16(expected) and value['valueSHA256'] == digest(expected), 'Wrong target fingerprint')


def attribute(value, key):
    require(type(value) is dict, 'Invalid attribute record')
    if value.get('state') == 'UNKNOWN':
        exact(value, ['state', 'type'])
        require(value['type'] in ['absent', 'dictionary', 'unsupported'], 'Unknown attribute type')
        return
    require(value.get('state') == 'OBSERVED', 'Invalid attribute state')
    if key in ['font', 'accessibilityFont']:
        require(value.get('type') in ['NSFont', 'AXFontDictionary'], 'Reference/wrong font type')
        required = {'state', 'type', 'name', 'pointSize'} | ({'traits'} if value['type'] == 'NSFont' else set())
        require(required <= set(value) <= required | ({'family', 'visibleName'} if value['type'] == 'AXFontDictionary' else set()), 'Invalid font dictionary keys')
        for field in ['name', 'family', 'visibleName']:
            if field in value:
                require(type(value[field]) is str and 0 < utf16(value[field]) <= 128, 'Invalid/big font name')
        require(number(value['pointSize']) and value['pointSize'] > 0, 'Invalid actual font size')
        if 'traits' in value:
            require(integer(value['traits']), 'Invalid font traits')
    else:
        exact(value, ['state', 'type', 'components'])
        require(value['type'] == 'sRGB' and type(value['components']) is list and len(value['components']) == 4 and all(number(c) and 0 <= c <= 1 for c in value['components']), 'Invalid public color')


def target(value, spec, main, sheet, issues):
    kind, identifier, pane, text, in_sheet = spec
    required = {'kind', 'identifier', 'pane', 'expectedUTF16Length', 'expectedSHA256', 'state', 'reason', 'matchCount', 'matchScope', 'attributedCall'}
    optional = {'wrapper', 'queried', 'queryKind', 'requestedRange', 'returnedUTF16Length', 'returnedSHA256', 'runs', 'attributedScope'}
    require(type(value) is dict and required <= set(value) <= required | optional, 'Unknown/missing target keys')
    require([value[k] for k in ['kind', 'identifier', 'pane', 'expectedUTF16Length', 'expectedSHA256']] == [kind, identifier, pane, utf16(text), digest(text)], 'Wrong selected target')
    require(type(value['expectedUTF16Length']) is int and integer(value['matchCount'], 0, 256) and value['state'] in ['UNKNOWN', 'OBSERVED'] and value['reason'] in REASONS, 'Invalid target state')
    owning_window = sheet if in_sheet else main
    root = 'attached-sheet' if in_sheet else 'main-content'
    observed = value['state'] == 'OBSERVED'
    require(type(value['matchScope']) is str and value['matchScope'] == 'visited-owned-public-nodes', 'Candidate count cannot establish global uniqueness')
    call = value['attributedCall']
    require(type(call) is str and call in ['not-run', 'completed-nil', 'completed-mismatched', 'completed-matched'], 'Uncompleted/unknown public call')
    called = call != 'not-run'
    scope = value.get('attributedScope')
    partial = scope == 'partial-owned-exact-wrapper'
    if called:
        require(scope in ['partial-owned-exact-wrapper', 'complete-public-traversal'] and value['matchCount'] == 1 and owning_window is not None, 'Unbound attributed call')
        require({'wrapper', 'queried', 'queryKind', 'requestedRange'} <= set(value), 'Missing called candidate')
        require(issues == ['unsupported-public-node'] and value['queryKind'] == 'exact-wrapper' and not observed if partial else not issues, 'Unsafe partial call or traversal')
        require(owning_window['visible'] is True and owning_window['number'] >= 0, 'Invalid called owning window')
        node(value['queried'], expected=text, pane=pane, root=root, owning_window=owning_window, observed=True)
        frame(value['wrapper']['frame'])
        require(value['wrapper']['frame'][2] > 0 and value['wrapper']['frame'][3] > 0 and contained(owning_window['frame'], value['wrapper']['frame']), 'Outside-window wrapper geometry')
    else:
        require(not {'attributedScope', 'requestedRange', 'returnedUTF16Length', 'returnedSHA256', 'runs'}.intersection(value), 'Unrun public call carries results')
    if call in ['completed-nil', 'completed-mismatched']:
        require(not observed and value['reason'] == 'unsupported-or-mismatched-attributed-string' and not {'returnedUTF16Length', 'returnedSHA256', 'runs'}.intersection(value), 'Nil/mismatched return carries matched data')
    if call == 'not-run':
        require(not observed and value['reason'] not in ['public-attributed-string', 'partial-public-attributed-string', 'unsupported-or-mismatched-attributed-string', 'invalid-attribute-range', 'run-limit'], 'Unrun call given return reason')
    if call == 'completed-matched':
        require({'returnedUTF16Length', 'returnedSHA256'} <= set(value), 'Missing matched return fingerprint')
        require(value['reason'] in ['public-attributed-string', 'partial-public-attributed-string', 'invalid-attribute-range', 'run-limit'], 'Wrong matched return reason')
        require(value['reason'] != 'public-attributed-string' or observed, 'Complete matched metadata requires observed target')
        require(('runs' in value) == (value['reason'] in ['public-attributed-string', 'partial-public-attributed-string']), 'Missing/invalid completed run data')
    if 'runs' in value:
        require(call == 'completed-matched' and value['reason'] == ('partial-public-attributed-string' if partial else 'public-attributed-string'), 'Unmatched/unqualified attribute runs')
    if value['reason'] == 'partial-public-attributed-string':
        require(partial and call == 'completed-matched' and 'runs' in value and not observed, 'Partial evidence cannot establish target observation')
    if observed:
        require(not issues and value['reason'] == 'public-attributed-string' and value['matchCount'] == 1 and owning_window is not None, 'Unqualified observed target')
        require(set(value) == required | optional and call == 'completed-matched' and scope == 'complete-public-traversal', 'Missing observed target data')
    else:
        require(value['reason'] != 'public-attributed-string', 'Unknown target given observed reason')
    for field in ['wrapper', 'queried']:
        if field in value:
            require(owning_window is not None, 'Target outside missing sheet')
            node(value[field], expected=text, pane=pane, root=root, owning_window=owning_window, observed=observed and field == 'queried')
    if 'queryKind' in value:
        require(value['queryKind'] in ['exact-wrapper', 'direct-rendered-static-text'], 'Unsupported query route')
        require('wrapper' in value and 'queried' in value, 'Missing queried identity')
        if value['queryKind'] == 'exact-wrapper':
            require(value['wrapper'] == value['queried'], 'Different exact wrapper query')
        else:
            require(value['queried']['role'] == 'AXStaticText' and value['queried']['path'][:-1] == value['wrapper']['path'], 'Wrong/non-direct rendered child')
    if 'requestedRange' in value:
        require(value['requestedRange'] == [0, utf16(text)] and all(type(v) is int for v in value['requestedRange']), 'Wrong/oversized text range')
    if 'returnedUTF16Length' in value:
        require(type(value['returnedUTF16Length']) is int and value['returnedUTF16Length'] == utf16(text) and value.get('returnedSHA256') == digest(text), 'Wrong attributed fingerprint')
    if 'runs' in value:
        runs = value['runs']
        require(type(runs) is list and 1 <= len(runs) <= 16, 'Run limit')
        position = 0
        for run in runs:
            exact(run, ['range', 'attributes'])
            r = run['range']
            require(type(r) is list and len(r) == 2 and integer(r[0]) and integer(r[1], 1) and r[0] == position and sum(r) <= utf16(text), 'Wrong/overlapping run')
            position += r[1]
            exact(run['attributes'], ATTRIBUTES)
            for key, attr in run['attributes'].items():
                attribute(attr, key)
        require(position == utf16(text), 'Incomplete text runs')


def validate_native_receipt(data, *, token, case, checkpoint, sequence, request_id, request_time, now):
    value = decode(data)
    exact(value, ['schema', 'token', 'case', 'checkpoint', 'sequence', 'requestID', 'uptime', 'auditQualified', 'contrastQualified', 'state', 'issues', 'visitedNodes', 'coordinateSpace', 'active', 'keyWindow', 'mainWindow', 'window', 'attachedSheet', 'orderedWindows', 'targets', 'screens', 'screenFrame'])
    request_binding(value, token, case, checkpoint, sequence, request_id)
    require(value['auditQualified'] is False and value['contrastQualified'] is False, 'Audit qualification/waiver prohibited')
    require(number(request_time) and number(now) and number(value['uptime']) and request_time <= value['uptime'] <= now and now-request_time <= 5, 'Stale receipt')
    require(value['state'] in ['UNKNOWN', 'OBSERVED'] and value['coordinateSpace'] == 'AppKit-screen-bottom-left' and type(value['active']) is bool, 'Invalid native state')
    require(integer(value['keyWindow'], -1) and integer(value['mainWindow'], -1) and integer(value['visitedNodes'], 0, 256), 'Invalid native bounds/identity')
    require(type(value['issues']) is list and len(value['issues']) <= 11 and all(type(i) is str and i in ISSUES for i in value['issues']) and len(set(value['issues'])) == len(value['issues']), 'Invalid traversal issues')
    require(value['state'] == ('UNKNOWN' if value['issues'] else 'OBSERVED'), 'Wrong traversal qualification')
    require(integer(value['screens'], 0, 256), 'Invalid screen count')
    frame(value['screenFrame'], nullable=True)
    window(value['window']); window(value['attachedSheet'], nullable=True)
    require(type(value['orderedWindows']) is list and len(value['orderedWindows']) <= 8 and all(integer(v, -1) for v in value['orderedWindows']), 'Window order bound')
    if value['state'] == 'OBSERVED':
        require(value['screens'] == 1 and value['screenFrame'] is not None, 'Unqualified screen identity')
        require(value['window']['visible'] is True and value['window']['frame'] is not None and value['window']['number'] >= 0, 'Invalid current window')
        if checkpoint == 'mac-chinese-policy':
            require(value['attachedSheet'] is not None and value['attachedSheet']['sheetParent'] == value['window']['number'] and value['window']['attachedSheet'] == value['attachedSheet']['number'], 'Wrong attached sheet')
        else:
            require(value['attachedSheet'] is None and value['window']['attachedSheet'] == -1, 'Unexpected sheet')
    specs = target_specs(case, checkpoint)
    require(type(value['targets']) is list and len(value['targets']) == len(specs) <= 8, 'Missing/duplicate targets')
    for observation, spec in zip(value['targets'], specs):
        target(observation, spec, value['window'], value['attachedSheet'], value['issues'])
    return value


def validate_observer_source(app_source, ui_source, release_source):
    """Lexical source/mutation contract only, explicitly not native compilation."""
    require('#if DEBUG\nimport CryptoKit\n' in app_source, 'Observer not Debug only')
    observer = app_source.split('private final class MacAuditPublicMetadataObserver', 1)[-1]
    required = ['MacSandboxDiagnostics.requested, MacSandboxDiagnostics.sandboxed', 'UUID(uuidString: token)?.uuidString == token',
                'Self.checkpoints[testCase] != nil', 'requests < 6', 'attempts < 6', 'bytes.count <= 1024', 'sequence == requests + 1',
                '!acceptedRequests.contains(requestID)', '!acceptedCheckpoints.contains(checkpoint)', 'requestTime >= started',
                'systemUptime - requestTime <= 5', 'data.count <= 32768', 'depth <= 16', 'visits < 256',
                'as? NSAccessibilityProtocol', 'view.window === root', 'ownWindow === root', 'active.contains(identity)',
                'matching.count == 1', 'wrapper.object.accessibilityValue() == nil', 'rendered.count == 1', '$0.path.count == wrapper.path.count + 1',
                'value.utf16.count <= 4096', 'runs.count < 16', 'targets.prefix(8)', 'accessibilityAttributedString(for: range)',
                'attributed.length == range.length, attributed.string == value', 'queried.root.frame.contains',
                '"auditQualified": false, "contrastQualified": false', 'typedPublicMetadataBooleans(encoded)',
                'CFGetTypeID(number) == CFBooleanGetTypeID()', 'event.keyCode == 25, !event.isARepeat',
                'intersection(.deviceIndependentFlagsMask) == flags', 'let eventWindow = event.window', 'eventWindow === root || eventWindow === root.attachedSheet',
                'NSEvent.addLocalMonitorForEvents(matching: .keyDown)', 'NSEvent.removeMonitor(monitor)', 'NSPasteboard(name:',
                'board.changeCount == change', 'guard issues.isEmpty || partial',
                'issues == Set(["unsupported-public-node"]) && queryKind == "exact-wrapper"',
                '"matchScope": "visited-owned-public-nodes"', '"attributedCall": "not-run"',
                'result["attributedCall"] = "completed-nil"', 'result["attributedCall"] = "completed-mismatched"',
                'result["attributedCall"] = "completed-matched"', 'partial ? "UNKNOWN" : "OBSERVED"', '"state": "UNKNOWN", "type": "absent"']
    for token in required:
        require(token in observer, 'Missing observer source guard: '+token)
    for forbidden in ['AXUIElement', 'AXIsProcessTrusted', 'value(forKey', 'performSelector', 'NSSelectorFromString', 'method_exchangeImplementations',
                      'addGlobalMonitor', 'CGEventTap', 'as? CGColor', 'as! CGColor', 'CFGetTypeID(value', 'NSPasteboard.general', 'NSPasteboard.find', 'setAccessibility', '.font(.', '.foregroundStyle(', 'preferredFont']:
        require(forbidden not in observer, 'Forbidden observer behavior: '+forbidden)
    candidate_gate = observer.index('guard issues.isEmpty || partial')
    verification = observer.index('guard let value = stringValue(queried.object)')
    range_gate = observer.index('result["requestedRange"] = [range.location, range.length]')
    public_call = observer.index('let returned = queried.object.accessibilityAttributedString(for: range)')
    complete = observer.index('result["attributedCall"] = "completed-matched"')
    require(candidate_gate < verification < range_gate < public_call < complete, 'Call must follow owned candidate value/frame verification')
    require('let partial = issues == Set(["unsupported-public-node"]) && queryKind == "exact-wrapper"\n            guard issues.isEmpty || partial else' in observer, 'Partial issue/route allowlist broadened')
    for token in ['target["matchScope"] as? String == "visited-owned-public-nodes"', 'issues == ["unsupported-public-node"]',
                  'value["state"] as? String == "UNKNOWN", target["state"] as? String == "UNKNOWN"',
                  '"not-run", "completed-nil", "completed-mismatched", "completed-matched"']:
        require(token in ui_source, 'Missing UI partial receipt guard: '+token)
    screenshot = ui_source.split('    private func screenshot(_ name: String) throws {', 1)[1].split('\n    func test', 1)[0]
    require(screenshot.startswith('\n        #if DEBUG\n        collectPublicMetadataIfSelected(name)\n        #endif\n        try capturePixels(name)'), 'Snapshot must precede unchanged capture/audit')
    for token in ['performAccessibilityAudit(for: .all)', 'XCTFail("Accessibility audit', 'return false', 'continueAfterFailure = previousFailureMode']:
        require(token in screenshot, 'Strict original audit missing')
    helper = ui_source.split('    #if DEBUG\n    private struct PublicMetadataSession', 1)[1].split('    #endif\n\n    private func capturePixels', 1)[0]
    require(helper.count('app.typeKey("9"') == 1 and 'sleep(' not in helper and 'waitForExistence' not in helper and 'while ' not in helper, 'Unbounded/repeated observer event')
    require('NSPasteboard.general.changeCount' in helper and 'NSPasteboard.general.string' not in helper and 'NSPasteboard.general.clearContents' not in helper, 'General clipboard data/mutation')
    require('QRCATCHER_MAC_PUBLIC_METADATA_DIAGNOSTIC' in helper and 'isSandboxedProduct' in helper and 'sameState' in helper, 'Missing exact test gate/pair')
    for marker in ['QRCATCHER_MAC_PUBLIC_METADATA_', 'QRCatcher.MacPublicMetadata.', 'org.qrcatcher.mac-public-metadata.', 'MacAuditPublicMetadataObserver', 'MAC_PUBLIC_METADATA_']:
        require(marker in release_source, 'Missing Release absence gate')
    return True


def validate_paired_receipt(data, *, token, case, checkpoint, sequence, request_id, request_time, now):
    value = decode(data)
    required = {'schema', 'token', 'case', 'checkpoint', 'sequence', 'requestID', 'auditQualified', 'contrastQualified', 'sameState', 'reason'}
    optional = {'native', 'paired', 'generalChangeCountUnchanged'}
    require(type(value) is dict and required <= set(value) <= required | optional, 'Unknown paired keys')
    request_binding(value, token, case, checkpoint, sequence, request_id)
    require(value['auditQualified'] is False and value['contrastQualified'] is False, 'Paired audit waiver prohibited')
    require(value['sameState'] in ['UNKNOWN', 'OBSERVED'] and value['reason'] in ['missing-or-invalid-receipt', 'state-or-geometry-mismatch', 'oversized-paired-receipt', 'bounded-public-pair'], 'Unknown pair state/reason')
    if 'native' not in value:
        require(value['sameState'] == 'UNKNOWN' and value['reason'] in ['missing-or-invalid-receipt', 'oversized-paired-receipt'] and 'paired' not in value, 'Missing observed native receipt')
        return value
    native = validate_native_receipt(json.dumps(value['native'], allow_nan=False).encode(), token=token, case=case, checkpoint=checkpoint,
                                     sequence=sequence, request_id=request_id, request_time=request_time, now=now)
    require('paired' in value and type(value.get('generalChangeCountUnchanged')) is bool, 'Missing pair/changeCount observation')
    paired = value['paired']
    exact(paired, ['windows', 'mainWindowMatches', 'windowFrame', 'sheets', 'dialogs', 'foreground', 'screenFrame', 'targets', 'screens', 'coordinateSpace'])
    require(integer(paired['screens'], 0, 256) and paired['coordinateSpace'] == 'XCTest-screen-top-left', 'Invalid paired screen identity')
    require(all(integer(paired[k], 0, 256) for k in ['windows', 'mainWindowMatches', 'sheets', 'dialogs']) and type(paired['foreground']) is bool, 'Bad paired native state')
    for field in ['windowFrame', 'screenFrame']:
        if paired[field] != []:
            frame(paired[field])
    specs = target_specs(case, checkpoint)
    require(type(paired['targets']) is list and len(paired['targets']) == len(specs), 'Wrong paired target inventory')
    for row, spec in zip(paired['targets'], specs):
        keys = {'kind', 'matches'}
        require(type(row) is dict and keys <= set(row) <= keys | {'frame', 'valueUTF16Length', 'valueSHA256'} and row['kind'] == spec[0] and integer(row['matches'], 0, 256), 'Wrong paired target')
        if set(row) != keys:
            require(set(row) == keys | {'frame', 'valueUTF16Length', 'valueSHA256'} and row['matches'] == 1, 'Incomplete paired fingerprint')
            frame(row['frame'])
            require(integer(row['valueUTF16Length'], 0, 4096) and type(row['valueSHA256']) is str and re.fullmatch(r'[0-9a-f]{64}', row['valueSHA256']), 'Invalid paired fingerprint')
    if value['sameState'] == 'OBSERVED':
        require(value['reason'] == 'bounded-public-pair' and value['generalChangeCountUnchanged'] is True and native['state'] == 'OBSERVED' and native['active'] is True, 'Unqualified pair')
        require(paired['windows'] == 1 and paired['mainWindowMatches'] == 1 and paired['dialogs'] == 0 and paired['foreground'] is True and paired['sheets'] == (1 if checkpoint == 'mac-chinese-policy' else 0), 'Changed paired state')
        expected_key = native['attachedSheet']['number'] if checkpoint == 'mac-chinese-policy' else native['window']['number']
        require(native['mainWindow'] == native['window']['number'] and native['keyWindow'] == expected_key, 'Changed key/main window')
        screen = paired['screenFrame']
        require(paired['screens'] == 1 and native['screens'] == 1 and len(screen) == 4 and screen[:2] == [0, 0] and native['screenFrame'] == screen, 'Unsupported screen coordinate conversion')
        def equal_frames(native_frame, ui):
            require(len(ui) == 4 and native_frame is not None, 'Missing paired frame')
            converted = [ui[0], screen[3]-ui[1]-ui[3], ui[2], ui[3]]
            require(all(abs(a-b) <= 2 for a, b in zip(native_frame, converted)), 'Changed paired geometry')
        equal_frames(native['window']['frame'], paired['windowFrame'])
        for target_value, row, spec in zip(native['targets'], paired['targets'], specs):
            require(target_value['state'] == 'OBSERVED' and row['matches'] == 1 and row.get('valueUTF16Length') == utf16(spec[3]) and row.get('valueSHA256') == digest(spec[3]), 'Wrong paired text')
            equal_frames(target_value['wrapper']['frame'], row.get('frame', []))
    else:
        require(value['reason'] != 'bounded-public-pair', 'Unknown pair mislabeled observed')
    return value
