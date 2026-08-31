import pytest


@pytest.mark.api_dev
def test_projects(authenticated_client):
    with authenticated_client as client:
        projects = client.account.projects()
        assert len(projects) > 0
        assert all(p.id for p in projects)


@pytest.mark.api_dev
def test_project_usage(authenticated_client):
    with authenticated_client as client:
        projects = client.account.projects()
        if not projects:
            return
        project_id = projects[0].id
        project = client.account.project(project_id)
        assert project.id == project_id

        allocations = client.account.project_allocations(project_id)
        # Allocations may be empty for a fresh project.
        for allocation in allocations:
            assert allocation.id