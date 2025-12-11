
def test_city_defaults(city):
    assert city.wood == 500.0
    assert city.clay == 500.0
    assert city.iron == 500.0
    assert city.loyalty == 100.0
