"""Install verified static releases on the GDPeso EC2 host."""

import argparse
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request


ROOT = Path('/home/ubuntu/2026_3dsa_4_GDPeso')
BUCKET = 'msi-gdpeso-releases-173677044880-us-east-1'
INSTANCE = 'i-068efaae507c5294d'
REPOSITORY = 'FrancisIGP/BI-Capstone'
REPOSITORY_ID = '1448663628'
COMPRESSED_LIMIT = 16 * 1024 * 1024
EXPANDED_LIMIT = 32 * 1024 * 1024
SITE_MEMBER = re.compile(r'site/(?:[A-Za-z0-9_-][A-Za-z0-9._-]*/)*[A-Za-z0-9_-][A-Za-z0-9._-]*')
RELEASE_ID = re.compile(r'[a-f0-9]{40}-[0-9]{1,20}-[1-9][0-9]{0,3}')
HEX_256 = re.compile(r'[a-f0-9]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_archive(archive, args):
    require(archive.stat().st_size <= COMPRESSED_LIMIT, 'Compressed release exceeds limit')
    source = archive.read_bytes()
    require(digest(source) == args.sha256, 'Release checksum mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(source)) as compressed:
        expanded = compressed.read(EXPANDED_LIMIT + 1)
    require(len(expanded) <= EXPANDED_LIMIT, 'Expanded release exceeds limit')
    members = {}
    with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as package:
        for member in package:
            name = member.name
            require(len(members) < 1500 and name not in members, 'Too many or duplicate release members')
            require(member.isfile() and not member.issparse() and not (member.mode & 0o7000), 'Invalid archive member')
            require(name == 'manifest.json' or (len(name) <= 240 and SITE_MEMBER.fullmatch(name)), 'Unexpected archive path')
            require(not any(part in ('.', '..') for part in PurePosixPath(name).parts), 'Unsafe release path')
            members[name] = package.extractfile(member).read()
    require('manifest.json' in members and 'site/index.html' in members, 'Required release files are missing')
    manifest_bytes = members.pop('manifest.json')
    require(len(manifest_bytes) <= 512 * 1024, 'Manifest exceeds limit')
    manifest = json.loads(manifest_bytes)
    expected = {'repository': REPOSITORY, 'repository_id': REPOSITORY_ID,
                'revision': args.revision, 'run_id': args.run_id, 'run_attempt': args.run_attempt}
    require(all(str(manifest.get(k)) == v for k, v in expected.items()), 'Release identity mismatch')
    require(manifest.get('files') == {name: digest(data) for name, data in members.items()}, 'Release file checksum mismatch')
    return members


def verify_host():
    require(os.geteuid() == 0 and ROOT.resolve() == ROOT, 'Unexpected GDPeso host directory')
    for directory in (ROOT, ROOT / 'releases', ROOT / 'staging'):
        require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_uid == 0
                and not (directory.stat().st_mode & 0o022), 'Untrusted release directory')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    metadata = 'http://169.254.169.254/latest/'
    request = urllib.request.Request(metadata + 'api/token', method='PUT',
                                     headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'})
    with opener.open(request, timeout=3) as response:
        token = response.read().decode()
    request = urllib.request.Request(metadata + 'meta-data/instance-id', headers={'X-aws-ec2-metadata-token': token})
    with opener.open(request, timeout=3) as response:
        require(response.read().decode() == INSTANCE, 'Unexpected EC2 instance')


def download(key, destination):
    import boto3

    s3 = boto3.client('s3', region_name='us-east-1')
    response = s3.get_object(Bucket=BUCKET, Key=key, ExpectedBucketOwner='173677044880')
    require(response['ContentLength'] <= COMPRESSED_LIMIT, 'S3 release exceeds limit')
    received = 0
    with destination.open('xb') as output:
        for block in response['Body'].iter_chunks(chunk_size=1024 * 1024):
            received += len(block)
            require(received <= COMPRESSED_LIMIT, 'S3 response exceeds limit')
            output.write(block)
    require(received == response['ContentLength'], 'Incomplete S3 release')


def current_release(pointer):
    if not pointer.exists() and not pointer.is_symlink():
        return None
    target = pointer.resolve(strict=True)
    require(pointer.is_symlink() and target.parent == ROOT / 'releases'
            and RELEASE_ID.fullmatch(target.name), 'Invalid release pointer')
    return target


def switch(pointer, target):
    if target is None:
        pointer.unlink(missing_ok=True)
        return
    temporary = pointer.with_name('.' + pointer.name + '.next')
    temporary.symlink_to(Path('releases') / target.name, target_is_directory=True)
    os.replace(temporary, pointer)


def verify_served(members):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    targets = ['http://127.0.0.1:18052']
    if (ROOT / '.https-ready').is_file():
        targets.append('https://www.gdpeso.xyz')
    paths = ['site/index.html']
    paths.extend(sorted(name for name in members if name.endswith(('.js', '.css')))[:2])
    for target in targets:
        for path in paths:
            url = target + '/' + ('' if path == 'site/index.html' else path.removeprefix('site/'))
            request = urllib.request.Request(url, headers={'Host': 'www.gdpeso.xyz', 'Cache-Control': 'no-cache'})
            with opener.open(request, timeout=12) as response:
                require(response.status == 200 and response.read(len(members[path]) + 1) == members[path],
                        'Serving content does not match candidate')


def deploy(args):
    phase = 'preflight'
    try:
        verify_host()
        release_id = f'{args.revision}-{args.run_id}-{args.run_attempt}'
        require(RELEASE_ID.fullmatch(release_id) and HEX_256.fullmatch(args.sha256), 'Invalid release arguments')
        expected_key = f'gdpeso/releases/{args.revision}/{args.run_id}-{args.run_attempt}.tar.gz'
        require((args.local_archive and args.run_id == '0' and not args.artifact_key)
                or (not args.local_archive and int(args.run_id) > 0 and args.artifact_key == expected_key),
                'Invalid release source')
        require(shutil.disk_usage(ROOT).free > 128 * 1024 * 1024, 'Insufficient disk space')
        with (ROOT / '.deploy.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            pointer = ROOT / 'current'
            previous_pointer = ROOT / 'previous'
            current = current_release(pointer)
            old_previous = current_release(previous_pointer)
            if current and tuple(map(int, current.name.rsplit('-', 2)[1:])) > (int(args.run_id), int(args.run_attempt)):
                print('GDPeso deployment skipped: stale revision')
                return
            with tempfile.TemporaryDirectory(prefix=release_id + '-', dir=ROOT / 'staging') as temporary:
                workspace = Path(temporary)
                archive = args.local_archive or workspace / 'release.tar.gz'
                if not args.local_archive:
                    phase = 'download'
                    download(expected_key, archive)
                phase = 'validation'
                members = read_archive(archive, args)
                candidate = ROOT / 'releases' / release_id
                if current == candidate:
                    verify_served(members)
                    print(f'GDPeso deployment verified: {args.revision}')
                    return
                stage = workspace / 'payload'
                stage.mkdir(mode=0o755)
                for name, data in members.items():
                    output = stage / name
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with output.open('xb') as stream:
                        stream.write(data)
                    output.chmod(0o644)
                require(not candidate.exists() and not candidate.is_symlink(), 'Release attempt already exists')
                phase = 'activation'
                os.replace(stage, candidate)
                switched = False
                try:
                    switch(pointer, candidate)
                    switched = True
                    phase = 'verification'
                    verify_served(members)
                    (candidate / '.gdpeso-verified').touch(exist_ok=False)
                    switch(previous_pointer, current)
                except BaseException:
                    if switched:
                        switch(pointer, current)
                        switch(previous_pointer, old_previous)
                        if current:
                            verify_served({'site/index.html': (current / 'site/index.html').read_bytes()})
                    raise
                for old in (ROOT / 'releases').iterdir():
                    if (old not in (current, candidate) and RELEASE_ID.fullmatch(old.name)
                            and old.is_dir() and not old.is_symlink() and (old / '.gdpeso-verified').is_file()):
                        try:
                            shutil.rmtree(old)
                        except OSError:
                            pass  # Retention cleanup must not change a verified deployment outcome.
                print(f'GDPeso deployment verified: {args.revision}')
    except Exception as error:
        print(f'GDPeso deployment failed: {phase}')
        fd = os.open(ROOT / '.deploy-errors.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as log:
            print(f'{args.revision} {args.run_id}-{args.run_attempt} {phase}: {error!r}', file=log)
        raise SystemExit(1) from None


if __name__ == '__main__':
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-key')
    parser.add_argument('--local-archive', type=Path)
    for option in ('sha256', 'revision', 'run-id', 'run-attempt'):
        parser.add_argument('--' + option, required=True)
    deploy(parser.parse_args())
