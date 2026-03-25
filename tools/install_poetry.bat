@ECHO OFF
CALL CLS
@REM This script will help SETup for the first time
@REM Run it if you don't have poetry install or if
@REM you want to reinstall it.

@REM This is the version that will be installed.
SET "TARGET_POETRY_VERSION=2.3.2"

SETLOCAL ENABLEDELAYEDEXPANSION

@REM Check if poetry is installed
WHERE poetry >NUL 2>NUL

IF %ERRORLEVEL% EQU 0 (
    ECHO Poetry is installed.

    @REM Get poetry version
    for /f "tokens=3 delims= " %%v in ('poetry --version') do (
        SET "RAW_VERSION=%%v"
        @REM Remove parentheses using string substitution
        set "RAW_VERSION=!RAW_VERSION:(=!"
        set "RAW_VERSION=!RAW_VERSION:)=!"
        set "POETRY_VERSION=!RAW_VERSION!"

    )
    ECHO Installed version: !POETRY_VERSION!

    IF !POETRY_VERSION! EQU !TARGET_POETRY_VERSION! (
        @REM Do nothing!
    ) ELSE (
        ECHO Attempting to uninstall Poetry...
        CALL curl -sSL https://install.python-poetry.org | python - --uninstall
        ECHO Poetry has been removed.
        ECHO Installing poetry.
        CALL curl -sSL https://install.python-poetry.org | python - --version %TARGET_POETRY_VERSION%
    )
) ELSE (
    ECHO Poetry is not installed.
    ECHO Installing poetry.
    CALL curl -sSL https://install.python-poetry.org | python - --version %TARGET_POETRY_VERSION%
)

ECHO Adding certificates package to global poetry:
CALL poetry self add pip-system-certs==4.0
ECHO Forcing poetry to use certificates for prod server:
CALL poetry config certificates.arti_novpypi.cert true
ECHO Forcing poetry to use certificates for dev server:
CALL poetry config certificates.arti_dev_novpypi.cert true
ENDLOCAL
ECHO Poetry is ready to use on version: %TARGET_POETRY_VERSION%
PAUSE
