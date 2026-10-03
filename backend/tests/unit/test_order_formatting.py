from revenueflowai.agents.order import _money, _qty


def test_zero_estimated_value_is_rendered_as_money_not_scientific_notation():
    assert _money("0E-8") == "0.00"


def test_quantity_drops_trailing_zeros_but_keeps_real_fractions():
    assert _qty("5.0000") == "5"
    assert _qty("2.5000") == "2.5"
