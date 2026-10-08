"""Closed identities for four existing Vision cases, each on a fresh matrix VM.

Selection is explicit: no combined case, default case, retry, or trait fallback.
"""
from dataclasses import dataclass
import re
import uuid


@dataclass(frozen=True)
class Case:
    scope: str
    name: str
    result: str
    label: str
    seconds: int
    default_seconds: int
    maximum_seconds: int
    frames: tuple
    hosted_tests: bool
    photo_seed: bool
    files_fixture: bool
    release_package: bool
    evidence_bytes: int


_CHINESE = ('vision-chinese-empty', 'vision-chinese-result', 'vision-chinese-policy')
CASES = (
    Case('visionos_photos', 'testRealPhotosImportCopyAndReopen', 'VisionPhotosUIResults.xcresult',
         'photos-export', 600, 420, 480,
         ('vision-imported-qr', 'vision-reopened-history', 'vision-exported-qr', 'vision-exported-history'),
         True, True, False, False, 900000),
    Case('visionos_files', 'testRealFilesImportAndReopen', 'VisionFilesUIResults.xcresult',
         'files', 300, 420, 480, ('vision-files-import-reopened',), False, False, True, True, 800000),
    Case('visionos_chinese', 'testChineseEmptyPhotosResultAndOfflinePolicy', 'VisionChineseUIResults.xcresult',
         'chinese', 300, 420, 480, _CHINESE, False, True, False, False, 550000),
    Case('visionos_largest', 'testChineseEmptyPhotosResultAndOfflinePolicy', 'VisionLargestUIResults.xcresult',
         'largest', 300, 180, 240, _CHINESE, False, True, False, False, 550000),
)
SCOPES = frozenset(case.scope for case in CASES)


def select_case(scope):
    for case in CASES:
        if scope == case.scope:
            return case
    raise ValueError('Expected one exact Vision case scope; combined/default cases are forbidden')


def case_identity(case, source_commit, device):
    if case not in CASES or not isinstance(source_commit, str) or not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('Unexpected case/source identity')
    if not isinstance(device, str) or str(uuid.UUID(device)).upper() != device:
        raise ValueError('Expected an exact uppercase device UUID')
    return {'scope': case.scope, 'case': case.name, 'result': case.result,
            'source_commit': source_commit, 'device': device}


def require_identity(value, expected):
    if not isinstance(value, dict) or any(value.get(key) != item for key, item in expected.items()):
        raise ValueError('Vision evidence case/source/device/result identity mismatch')
