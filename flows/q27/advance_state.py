"""Q-27 feedback writer: emit a deterministic next-state JSON value."""

import json
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise TypeError("workflow Program input must be an object")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict) or "state" not in inputs:
        raise TypeError("workflow Program input must contain state")
    state = inputs["state"]
    if isinstance(state, dict):
        next_state = dict(state)
        epoch = next_state.get("epoch", 0)
        if type(epoch) is not int:
            raise TypeError("state.epoch must be an integer")
        next_state["epoch"] = epoch + 1
    else:
        next_state = {"previous": state, "epoch": 1}
    json.dump(next_state, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
