@ECHO OFF
CALL CLS
@REM This script will help setup after a new clone or check-out.
@REM For security reasons, git does not allow for it to run scripts
@REM automatically after cloning or check-out.

ECHO Checking if branch has proper version control setup:
CALL poetry lock

ECHO Forcing creation of poetry venv:
CALL poetry install --with dev --with test

ECHO Poetry venv ready to use!
PAUSE
CALL CLS

ECHO Installing pre-commit:
CALL poetry run pre-commit install

ECHO Running pre-commit to check if branch has proper pre-commit compatibility:
CALL poetry run pre-commit run --all-files

ECHO Repository ready!
ECHO Happy coding!
PAUSE
EXIT
