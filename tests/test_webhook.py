#!/usr/bin/env python
"""Test the webhook endpoint."""

def test_webhook():
    try:
        from api import main
        from fastapi.testclient import TestClient

        client = TestClient(main.app)
        response = client.post(
            '/github/webhook',
            headers={'X-GitHub-Event': 'pull_request'},
            json={
                'action': 'opened',
                'installation': {'id': 12345},
                'repository': {'owner': {'login': 'octo'}, 'name': 'example', 'full_name': 'octo/example'},
                'pull_request': {'number': 42, 'head': {'sha': 'abc123'}}
            }
        )
        print(f'Status: {response.status_code}')
        print(f'Response: {response.text}')
    except Exception as e:
        raise
