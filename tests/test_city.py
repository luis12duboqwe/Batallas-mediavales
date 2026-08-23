from app.services import balance


def test_city_defaults(city):
    assert {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    } == balance.CITY_STARTING_RESOURCES
    assert city.loyalty == 100.0
