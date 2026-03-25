"""Create a pylint report for the target package or module and save it to a log file."""

import re
import subprocess
import sys
from pathlib import Path

# Set your minimum acceptable score
MIN_SCORE = 8.0

# Target package or module to lint
TARGET = "gitlab_stats"

# Output log file path
log_path = Path("doc") / "pylint_report.txt"
log_path.parent.mkdir(parents=True, exist_ok=True)


def run_pylint(target):
    """Run pylint on the target and process the output.
    generates a report in doc/pylint_report.txt and prints the score to console."""
    try:
        result = subprocess.run(  # NOQA: S603
            ["pylint", target],  # NOQA: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        # remove old_value, differences and previous from tables in the report:
        _first_index_for_removal = 0
        _second_index_for_removal = 0
        _aux_stdout = []
        for _line in result.stdout.split("\n"):
            # find the indexes of previous:
            if (_aux := _line.find(r"previous |")) != -1:
                _first_index_for_removal = _aux
                _second_index_for_removal = 0
            # find the indexes of old number and difference:
            if (_aux := _line.find(_string := r"old number |difference |")) != -1:
                _first_index_for_removal = _aux
                _second_index_for_removal = _aux + len(_string)
            elif len(_line) == 0:
                # the table is over:
                _first_index_for_removal = 0
                _second_index_for_removal = 0
            # if there is just one index, remove the rest of the line:
            if _first_index_for_removal and not _second_index_for_removal:
                # remove the end of the line:
                _line = _line[:_first_index_for_removal]
            # if there is two index, cut that part of the line:
            elif _first_index_for_removal and _second_index_for_removal:
                # remove the middle of the line:
                _line = (
                    _line[:_first_index_for_removal] + _line[_second_index_for_removal:]
                )
            # remove trailing whitespace for each line:
            _aux_stdout.append(_line.strip())
        result.stdout = "\n".join(_aux_stdout)
        # replace only dashed lines to fixed size, so that reduces diff between runs:
        for dashed_line in re.findall(
            r"-+\n",
            result.stdout,
        ):
            result.stdout = (
                result.stdout.replace(
                    dashed_line,
                    "#-" * 39 + "#" + "\n",
                    1,
                ).strip()
                + "\n"
            )
        # Extract score from output
        # Your code has been rated at 8.21/10 (previous run: 8.21/10, +0.00)
        match = re.search(
            r"(Your code has been rated at ([\d\.]+)\/10 \(previous run: ([\d\.]+)\/10,.*\))",
            result.stdout,
        )
        # Print output to console
        print(result.stdout)
        if match:
            score = float(match.group(2))
            new_score_line = f"Your code has been rated at {score!s}"
            result.stdout = (
                result.stdout.replace(
                    match.group(1),
                    new_score_line,
                ).strip()
                + "\n"
            )
            # Write output to log file
            with open(log_path, "w", encoding="utf-8") as report_file:
                report_file.write(result.stdout)
            if score < MIN_SCORE:
                print(f"Pylint score {score} is below the minimum required {MIN_SCORE}")
                sys.exit(1)
            else:
                print(f"Pylint score {score} meets the minimum requirement.")
        else:
            print("Could not find pylint score in output.")
            sys.exit(1)
    except FileNotFoundError:
        print("Pylint is not installed or not found in PATH.")
        sys.exit(1)


if __name__ == "__main__":
    run_pylint(TARGET)
