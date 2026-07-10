from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
package_root = project_root / "src" / "conf_edit"

analysis = Analysis(
    [str(package_root / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(package_root / "templates"), "conf_edit/templates"),
        (str(package_root / "static"), "conf_edit/static"),
    ],
    hiddenimports=collect_submodules("sqlglot"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["playwright", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="ConfEdit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
