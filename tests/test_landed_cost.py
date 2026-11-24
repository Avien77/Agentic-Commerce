import pytest

from src.tools.landed_cost import compute_landed_cost


def test_in_person_pickup_has_zero_shipping():
    res = compute_landed_cost(price=45.0, shipping=None, delivery_type="in_person")
    assert res.shipping == 0.0
    assert res.shipping_estimated is False
    assert res.tax == 0.0
    assert res.total == 45.0


def test_unknown_shipping_uses_default_estimate():
    res = compute_landed_cost(price=45.0, shipping=None, delivery_type="shipping")
    assert res.shipping == 5.0
    assert res.shipping_estimated is True
    assert res.total == 50.0


def test_explicit_shipping_and_tax():
    res = compute_landed_cost(
        price=100.0,
        shipping=4.50,
        delivery_type="shipping",
        tax_rate=0.06,
    )
    assert res.shipping == 4.50
    assert res.shipping_estimated is False
    assert res.tax == 6.00
    assert res.total == 110.50


def test_negative_inputs_raise():
    with pytest.raises(ValueError):
        compute_landed_cost(price=-1.0)
    with pytest.raises(ValueError):
        compute_landed_cost(price=10.0, shipping=-2.0)
