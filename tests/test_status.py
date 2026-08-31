def test_incidents(unauthenticated_client):
    with unauthenticated_client as client:
        incidents = client.status.incidents()
        assert isinstance(incidents, list)
        for incident in incidents:
            assert incident.id


def test_events(unauthenticated_client):
    with unauthenticated_client as client:
        events = client.status.events()
        assert isinstance(events, list)
        for event in events:
            assert event.id


def test_resources_status(unauthenticated_client):
    with unauthenticated_client as client:
        resources = client.status.resources()
        assert len(resources) > 0
        for r in resources:
            assert r.name