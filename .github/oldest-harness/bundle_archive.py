#!/usr/bin/env python3
"""Bounded, digest-verified transport of unsigned simulator app bundles only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

MAX_ZIP = 15_000_000
MAX_RAW = 180_000_000
MAX_FILE = 96_000_000
MAX_ENTRIES = 20_000
MAX_MANIFEST = 3_000_000
EXPECTED = {"Celluloid.app", "QRCatcher.app", "TouchColor.app"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def checked_name(name):
    p = PurePosixPath(name)
    if (not name or "\\" in name or "\x00" in name or p.is_absolute()
            or any(x in ("", ".", "..") for x in name.split("/"))
            or p.parts[0] not in EXPECTED):
        raise ValueError("Invalid app member path")
    return p


def pack(apps, provenance, output):
    if output.exists():
        raise ValueError("Output already exists")
    if not apps or len({p.name for p in apps}) != len(apps):
        raise ValueError("Missing or duplicate app bundle")
    records, sources, total = {}, {}, 0
    for root in apps:
        if root.name not in EXPECTED or root.is_symlink() or not root.is_dir():
            raise ValueError("Unexpected app bundle")
        for path in sorted(root.rglob("*")):
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("Only regular app files and directories allowed")
            if path.is_dir():
                continue
            name = root.name + "/" + path.relative_to(root).as_posix()
            checked_name(name)
            if path.name == "embedded.mobileprovision" or path.suffix.lower() in (".p8", ".p12", ".pfx", ".key"):
                raise ValueError("Signing material is outside the unsigned simulator artifact")
            size = path.stat().st_size
            total += size
            if size > MAX_FILE or total > MAX_RAW or len(records) >= MAX_ENTRIES:
                raise ValueError("App payload exceeds bounds")
            records[name] = {"size": size, "sha256": digest(path), "executable": bool(mode & 0o111)}
            sources[name] = path
    manifest = {"format": 1, "kind": "sdk27-release-simulator-apps", "provenance": provenance, "files": records}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if not records or len(encoded) > MAX_MANIFEST:
        raise ValueError("Missing files or oversized manifest")
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", encoded)
            for name, path in sources.items():
                # Re-read and recheck immediately before archiving rather than trusting
                # a preflight record if a build product changed in the meantime.
                data = path.read_bytes()
                record = records[name]
                if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                    raise ValueError("App file changed during packaging")
                archive.writestr(name, data)
        if output.stat().st_size > MAX_ZIP:
            raise ValueError("Compressed app artifact exceeds 15 MB")
    except BaseException:
        # Keep partial output for diagnosis. The failed command prevents uploading;
        # no cleanup may delete a path another process created after preflight.
        raise
    return {"sha256": digest(output), "bytes": output.stat().st_size, "raw_bytes": total, "files": len(records)}


def inspect(archive_path, expected_sha):
    if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size > MAX_ZIP:
        raise ValueError("Invalid or oversized archive")
    if len(expected_sha) != 64 or digest(archive_path) != expected_sha:
        raise ValueError("Outer artifact digest mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names = [m.filename for m in members]
        if len(members) > MAX_ENTRIES + 1 or len(set(names)) != len(names) or names.count("manifest.json") != 1:
            raise ValueError("Invalid member inventory")
        manifest_entry = archive.getinfo("manifest.json")
        if manifest_entry.file_size > MAX_MANIFEST:
            raise ValueError("Oversized manifest")
        manifest = json.loads(archive.read(manifest_entry))
        if manifest.get("format") != 1 or manifest.get("kind") != "sdk27-release-simulator-apps":
            raise ValueError("Unsupported artifact format")
        records = manifest.get("files")
        if not isinstance(records, dict) or not records or set(records) != set(names) - {"manifest.json"}:
            raise ValueError("Manifest member inventory mismatch")
        total = 0
        for m in members:
            mode = m.external_attr >> 16
            if m.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or m.is_dir():
                raise ValueError("Encrypted or non-regular member rejected")
            if m.filename == "manifest.json":
                continue
            checked_name(m.filename)
            record = records[m.filename]
            total += m.file_size
            if (m.file_size > MAX_FILE or total > MAX_RAW or record.get("size") != m.file_size
                    or type(record.get("executable")) is not bool):
                raise ValueError("Member size or mode mismatch")
            h = hashlib.sha256()
            with archive.open(m) as stream:
                for data in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(data)
            if h.hexdigest() != record.get("sha256"):
                raise ValueError("Member digest mismatch")
        return manifest


def unpack(archive_path, expected_sha, destination):
    manifest = inspect(archive_path, expected_sha)
    # Caller provides a new job-temporary directory. Refuse reused paths/symlinks.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    with zipfile.ZipFile(archive_path) as archive:
        for name, record in manifest["files"].items():
            target = destination.joinpath(*checked_name(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output, archive.open(name) as source:
                for data in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(data)
            target.chmod(0o755 if record["executable"] else 0o644)
            if target.stat().st_size != record["size"] or digest(target) != record["sha256"]:
                raise ValueError("Extracted member changed")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_directory(root, manifest):
    expected = set(manifest["files"]) | {"manifest.json"}
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if not p.is_dir()}
    if actual != expected or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("App input member inventory changed")
    for name, record in manifest["files"].items():
        path = root.joinpath(*checked_name(name).parts)
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record["size"] or digest(path) != record["sha256"]:
            raise ValueError("Installed-input app bytes differ from producer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("pack")
    p.add_argument("--provenance", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("apps", type=Path, nargs="+")
    p = commands.add_parser("unpack")
    p.add_argument("archive", type=Path)
    p.add_argument("sha256")
    p.add_argument("destination", type=Path)
    p = commands.add_parser("verify")
    p.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "pack":
        print(json.dumps(pack(args.apps, json.loads(args.provenance.read_text()), args.output), sort_keys=True))
    elif args.command == "unpack":
        manifest = unpack(args.archive, args.sha256, args.destination)
        print(json.dumps({"verified_files": len(manifest["files"]), "provenance": manifest["provenance"]}, sort_keys=True))
    else:
        manifest = json.loads((args.directory / "manifest.json").read_text())
        verify_directory(args.directory, manifest)
        print("App input byte verification passed")
