"""Q-27 terminal predicate: always emit the strict JSON Boolean false."""

import json
import sys


def main() -> None:
    # Consume the contract so this is a real Program execution, while keeping
    # the predicate deterministic and strictly Boolean on every invocation.
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or not isinstance(payload.get("inputs"), dict):
        raise TypeError("workflow Program input must contain an inputs object")
    json.dump(False, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
