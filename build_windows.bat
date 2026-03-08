@echo off
setlocal

REM Build optimized exam client (prefer onedir for faster startup and smaller onefile penalty)
REM Optional: install UPX and set UPX_DIR to enable extra compression.

set ENTRY=exam_client.py
set DIST=dist_exam
set WORK=build_exam
set SPEC=spec_exam

if not "%UPX_DIR%"=="" (
  echo Using UPX: %UPX_DIR%
  pyinstaller --noconfirm --clean --windowed --onedir --name ExamClient ^
    --distpath %DIST% --workpath %WORK% --specpath %SPEC% ^
    --upx-dir "%UPX_DIR%" ^
    --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DRender --exclude-module PySide6.QtQuick3D ^
    %ENTRY%
) else (
  echo UPX_DIR not set, building without UPX compression.
  pyinstaller --noconfirm --clean --windowed --onedir --name ExamClient ^
    --distpath %DIST% --workpath %WORK% --specpath %SPEC% ^
    --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DRender --exclude-module PySide6.QtQuick3D ^
    %ENTRY%
)

echo Build done: %DIST%\ExamClient\ExamClient.exe
endlocal
