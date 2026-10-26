

def test_responds_to_keys():
    from oolite_ui_test_framework import outcomes as o
    assert o.check_responds_to_keys({"input_changed": 0.2})[0] == o.PASSED
    assert o.check_responds_to_keys({"input_changed": 0.0})[0] == o.FAILED
    assert o.check_responds_to_keys({})[0] == o.SKIPPED
    assert o.check_responds_to_keys({"exited": 1, "input_changed": 0.3})[0] == o.FAILED
