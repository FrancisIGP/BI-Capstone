"""Build or verify the bounded, deterministic GDPeso static release archive."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

MAX_COMPRESSED_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 29 * 1024 * 1024  # Leave room for tar headers under the host's 32 MiB limit.
MAX_MEMBERS = 1500
MAX_FILE_BYTES = MAX_EXPANDED_BYTES
SITE_MEMBER = re.compile(r'site/(?:[A-Za-z0-9_-][A-Za-z0-9._-]*/)*[A-Za-z0-9_-][A-Za-z0-9._-]*')
REPOSITORY = "FrancisIGP/BI-Capstone"
REPOSITORY_ID = "1448663628"
MANIFEST_NAME = "manifest.json"


class PackageError(ValueError):
    """Raised for invalid metadata or unsafe release archive contents."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata_from_env() -> dict[str, str]:
    values = {
        "repository": os.getenv("GITHUB_REPOSITORY", ""),
        "repository_id": os.getenv("GITHUB_REPOSITORY_ID", ""),
        "revision": os.getenv("GITHUB_SHA", ""),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "ref": os.getenv("GITHUB_REF", ""),
    }
    validate_metadata(values)
    return {key: values[key] for key in ("repository", "repository_id", "revision", "run_id", "run_attempt")}


def validate_metadata(metadata: dict[str, str]) -> None:
    expected_keys = {"repository", "repository_id", "revision", "run_id", "run_attempt"}
    if set(metadata) not in (expected_keys, expected_keys | {"ref"}):
        raise PackageError("Manifest metadata has unexpected keys")
    if metadata["repository"] != REPOSITORY or metadata["repository_id"] != REPOSITORY_ID:
        raise PackageError("GitHub repository identity does not match GDPeso production")
    if not re.fullmatch(r"[0-9a-f]{40}", metadata["revision"]):
        raise PackageError("Revision must be a 40-character lowercase commit hash")
    for key, max_digits in (("run_id", 20), ("run_attempt", 4)):
        if not re.fullmatch(r"[1-9][0-9]*", metadata[key]) or len(metadata[key]) > max_digits:
            raise PackageError(f"{key} must be a bounded positive integer string")
    if "ref" in metadata and metadata["ref"] != "refs/heads/main":
        raise PackageError("Release packages can only be built from refs/heads/main")


def is_secret_like(path: PurePosixPath) -> bool:
    forbidden_suffixes = {".pem", ".key", ".p12", ".pfx", ".p8", ".jks", ".keystore", ".db", ".sqlite", ".sqlite3", ".dump"}
    for part in path.parts:
        lower = part.lower()
        if lower.startswith(".env") or lower in {".aws", ".ssh"}:
            return True
        if any(word in lower for word in ("secret", "credential", "password", "privatekey", "id_rsa")):
            return True
        if Path(lower).suffix in forbidden_suffixes:
            return True
    return False


def validate_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or path.as_posix() != name
            or any(not part or part in {".", ".."} for part in name.split("/"))
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise PackageError("Archive contains a non-canonical or unsafe path")
    if name != MANIFEST_NAME and (len(name) > 240 or not SITE_MEMBER.fullmatch(name)):
        raise PackageError("Archive path does not match the host contract")
    return path


def collect_dist_files(dist: Path) -> list[tuple[Path, str]]:
    if dist.is_symlink() or not dist.is_dir():
        raise PackageError("Required dist directory is missing or unsafe")
    files: list[tuple[Path, str]] = []
    for current, dirs, names in os.walk(dist, followlinks=False):
        here = Path(current)
        for name in list(dirs):
            child = here / name
            if child.is_symlink() or not child.is_dir():
                raise PackageError(f"Symlink or non-directory entry is not allowed: {child.relative_to(dist).as_posix()}")
        for name in names:
            child = here / name
            relative = child.relative_to(dist).as_posix()
            member = validate_member_name(PurePosixPath("site", relative).as_posix())
            if child.is_symlink() or not stat.S_ISREG(child.lstat().st_mode):
                raise PackageError(f"Only regular files are allowed: {relative}")
            size = child.stat().st_size
            if size > MAX_FILE_BYTES:
                raise PackageError(f"File exceeds {MAX_FILE_BYTES} bytes: {relative}")
            if is_secret_like(member):
                raise PackageError(f"Secret-like path is not allowed: {relative}")
            files.append((child, member.as_posix()))
    if not files:
        raise PackageError("dist contains no files")
    return sorted(files, key=lambda item: item[1])


def manifest_for(files: list[tuple[Path, str]], metadata: dict[str, str]) -> dict:
    validate_metadata(metadata)
    return {
        **metadata,
        "files": {name: sha256_file(path) for path, name in files},
    }


def build_package(root: Path, output: Path, metadata: dict[str, str] | None = None) -> dict:
    root = root.resolve(strict=True)
    output = output.resolve()
    if output == root or root in output.parents:
        raise PackageError("Output archive must be outside the source tree")
    files = collect_dist_files(root / "dist")
    expanded = sum(path.stat().st_size for path, _ in files)
    if expanded > MAX_EXPANDED_BYTES:
        raise PackageError(f"Expanded package exceeds {MAX_EXPANDED_BYTES} bytes")
    if len(files) + 1 > MAX_MEMBERS:
        raise PackageError(f"Package exceeds {MAX_MEMBERS} members")
    manifest = manifest_for(files, metadata if metadata is not None else metadata_from_env())
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with temp.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                    for path, name in files:
                        info = tarfile.TarInfo(name)
                        info.size = path.stat().st_size
                        info.mode = 0o644
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        with path.open("rb") as stream:
                            archive.addfile(info, stream)
                    info = tarfile.TarInfo(MANIFEST_NAME)
                    info.size = len(manifest_bytes)
                    info.mode = 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(manifest_bytes))
        compressed_size = temp.stat().st_size
        if compressed_size > MAX_COMPRESSED_BYTES:
            raise PackageError(f"Compressed package exceeds {MAX_COMPRESSED_BYTES} bytes")
        temp.replace(output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return {"sha256": sha256_file(output), "compressed_bytes": compressed_size,
            "expanded_bytes": expanded, "members": len(files) + 1, "manifest": manifest}


def verify_package(archive_path: Path, expected: dict[str, str]) -> dict:
    validate_metadata(expected)
    if archive_path.stat().st_size > MAX_COMPRESSED_BYTES:
        raise PackageError("Compressed package exceeds the archive limit")
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_MEMBERS:
                raise PackageError("Archive member count is invalid")
            names: set[str] = set()
            total = 0
            file_hashes: dict[str, str] = {}
            manifest_data = None
            for member in members:
                name = member.name
                path = validate_member_name(name)
                if name in names:
                    raise PackageError("Archive contains a duplicate path")
                names.add(name)
                if not member.isfile() or member.issym() or member.islnk() or member.size < 0:
                    raise PackageError("Archive contains a non-regular file")
                source = archive.extractfile(member)
                if source is None:
                    raise PackageError("Archive member could not be read")
                data = source.read(MAX_FILE_BYTES + 1)
                if len(data) != member.size or len(data) > MAX_FILE_BYTES:
                    raise PackageError("Archive member size is invalid")
                if name == MANIFEST_NAME:
                    manifest_data = data
                    continue
                if not name.startswith("site/") or is_secret_like(path):
                    raise PackageError("Archive contains a non-runtime or secret-like path")
                total += len(data)
                if total > MAX_EXPANDED_BYTES:
                    raise PackageError("Expanded package exceeds the archive limit")
                file_hashes[name] = sha256_bytes(data)
            if manifest_data is None:
                raise PackageError("Archive manifest is missing")
            manifest = json.loads(manifest_data)
    except (tarfile.TarError, OSError, json.JSONDecodeError) as exc:
        raise PackageError("Archive is invalid") from exc
    if set(manifest) != {"repository", "repository_id", "revision", "run_id", "run_attempt", "files"}:
        raise PackageError("Manifest keys are invalid")
    identity = {key: manifest[key] for key in ("repository", "repository_id", "revision", "run_id", "run_attempt")}
    validate_metadata(identity)
    if identity != expected:
        raise PackageError("Artifact identity does not match this workflow run")
    listed = manifest["files"]
    if not isinstance(listed, dict) or listed != file_hashes:
        raise PackageError("Archive contents do not match the manifest")
    if not file_hashes:
        raise PackageError("Archive contains no site files")
    return {"sha256": sha256_file(archive_path), "manifest": manifest,
            "members": len(members), "expanded_bytes": total}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    for key in ("repository", "repository-id", "revision", "run-id", "run-attempt"):
        verify.add_argument(f"--{key}", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_package(args.root, args.output)
        else:
            expected = {"repository": args.repository, "repository_id": args.repository_id,
                        "revision": args.revision, "run_id": args.run_id, "run_attempt": args.run_attempt}
            result = verify_package(args.archive, expected)
        print(json.dumps({key: result[key] for key in ("sha256", "compressed_bytes", "expanded_bytes", "members") if key in result}, sort_keys=True))
        return 0
    except (OSError, PackageError, KeyError, TypeError) as exc:
        print(f"package error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
