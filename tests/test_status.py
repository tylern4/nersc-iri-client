def test_incidents(public_client):
    with public_client as client:
        incidents = client.status.incidents()
        assert isinstance(incidents, list)
        for incident in incidents:
            assert incident.id


def test_events(public_client):
    with public_client as client:
        events = client.status.events()
        assert isinstance(events, list)
        for event in events:
            assert event.id


def test_resources_status(public_client):
    with public_client as client:
        resources = client.status.resources()
        assert len(resources) > 0
        for r in resources:
            assert r.name