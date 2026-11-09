"""Build a self-contained macOS app from an installed, official OpenBot app."""
import argparse
import hashlib
import json
import os
import pathlib
import plistlib
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-app', type=pathlib.Path, default=pathlib.Path('/Applications/OpenBot.app'))
    parser.add_argument('--output-dir', type=pathlib.Path, default=pathlib.Path('dist'))
    parser.add_argument('--dmg', action='store_true', help='Also create a drag-and-drop DMG')
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    source = args.source_app.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    source_info = plistlib.loads((source / 'Contents/Info.plist').read_bytes())
    if source_info.get('CFBundleIdentifier') != 'app.openbot.desktop':
        raise ValueError('--source-app must point to an official OpenBot app')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(source)], check=True)
    bundle = output / 'OpenBot Custom.app'
    if bundle.exists():
        raise FileExistsError(f'{bundle} already exists; select a fresh --output-dir')
    macos = bundle / 'Contents/MacOS'
    resources = bundle / 'Contents/Resources'
    macos.mkdir(parents=True)
    resources.mkdir()
    config = resources / 'openbot-main-config'
    config.mkdir()
    for name in ('grok-main', 'acp_bridge.py', 'bridge_policy.py'):
        shutil.copy2(root / 'src' / name, config / name)
    for name in ('coordinator.md', 'main-grok.toml'):
        shutil.copy2(root / 'config' / name, config / name)
    shutil.copy2(root / 'config/settings.example.json', resources / 'settings.example.json')
    shutil.copy2(source / 'Contents/Resources/icon.icns', resources / 'icon.icns')
    archive = resources / 'OpenBot-runtime.zip'
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                    str(source), str(archive)], check=True)
    if plistlib.loads((source / 'Contents/Info.plist').read_bytes()) != source_info:
        raise RuntimeError('The source app changed while packaging; rebuild from a stable version')
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    manifest = {'openbotVersion': source_info['CFBundleShortVersionString'],
                'archiveSHA256': digest.hexdigest(), 'archiveBytes': archive.stat().st_size}
    (resources / 'runtime-build.json').write_text(json.dumps(manifest, indent=2))
    info = {
        'CFBundleName': 'OpenBot Custom', 'CFBundleDisplayName': 'OpenBot Custom',
        'CFBundleIdentifier': 'io.github.chujordyn.openbot-custom',
        'CFBundleExecutable': 'OpenBotStandalone', 'CFBundlePackageType': 'APPL',
        'CFBundleInfoDictionaryVersion': '6.0', 'CFBundleShortVersionString': '2.0.0',
        'CFBundleVersion': '2', 'CFBundleIconFile': 'icon.icns',
        'LSMinimumSystemVersion': '13.0', 'LSApplicationCategoryType': 'public.app-category.productivity',
        'LSUIElement': True, 'NSHighResolutionCapable': True,
    }
    (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    environment = dict(os.environ)
    environment.setdefault('CLANG_MODULE_CACHE_PATH', str(output / 'module-cache'))
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fmodules', '-Wall', '-Wextra',
                    '-mmacosx-version-min=13.0', '-framework', 'Cocoa',
                    str(root / 'macos/main.m'), '-o', str(macos / 'OpenBotStandalone')],
                   check=True, env=environment)
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(bundle)], check=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
    if args.dmg:
        staging = output / 'dmg-staging'
        staging.mkdir()
        subprocess.run(['/usr/bin/ditto', str(bundle), str(staging / bundle.name)], check=True)
        (staging / 'Applications').symlink_to('/Applications', target_is_directory=True)
        image = output / 'OpenBot-Custom-2.0.0.dmg'
        subprocess.run(['/usr/bin/hdiutil', 'create', '-volname', 'OpenBot Custom',
                        '-srcfolder', str(staging), '-format', 'UDZO', str(image)], check=True)
        subprocess.run(['/usr/bin/hdiutil', 'verify', str(image)], check=True)
    print(json.dumps({'bundle': str(bundle), **manifest}, indent=2))


if __name__ == '__main__':
    main()
