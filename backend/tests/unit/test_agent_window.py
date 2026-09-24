"""The model sees the last N turns, cut on turn boundaries."""

from app.agent.graph import window


def test_window_cuts_on_turn_boundaries():
    msgs = [{"i": i} for i in range(10)]
    turns = [0, 3, 7]
    assert window(msgs, turns, keep=2) == msgs[3:]
    assert window(msgs, turns, keep=3) == msgs
    assert window(msgs, turns, keep=0) == msgs
