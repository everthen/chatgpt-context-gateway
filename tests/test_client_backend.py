from pathlib import Path
from unittest.mock import MagicMock

from context_gateway.client import ChatGPTClient

def test_proven_chatgpt_project_endpoints_and_headers(tmp_path: Path):
    client = ChatGPTClient(
        access_token="token-value",
        account_id="acct-value",
        cookie="session=cookie-value",
    )
    mock = MagicMock()
    mock.request.side_effect = [
        MagicMock(
            status_code=200,
            ok=True,
            json=lambda: {
                "items": [
                    {
                        "gizmo": {
                            "gizmo": {
                                "id": "proj-1",
                                "display": {"name": "Project One"},
                                "created_at": 1,
                            }
                        }
                    }
                ],
                "cursor": None,
            },
        ),
        MagicMock(
            status_code=200,
            ok=True,
            json=lambda: {
                "items": [{"id": "conv-1", "title": "Chat One"}],
                "cursor": None,
            },
        ),
        MagicMock(
            status_code=200,
            ok=True,
            json=lambda: {"id": "conv-1", "title": "Chat One", "mapping": {}},
        ),
    ]
    client.session = mock

    projects = client.list_projects()
    assert projects[0]["id"] == "proj-1"
    assert projects[0]["name"] == "Project One"

    conversations = client.list_conversations(project_id="proj-1")
    assert conversations["items"][0]["id"] == "conv-1"

    conversation = client.get_conversation("conv-1")
    assert conversation["id"] == "conv-1"

    calls = mock.request.call_args_list
    assert calls[0].args[0] == "GET"
    assert calls[0].args[1].endswith("/gizmos/snorlax/sidebar")
    assert calls[1].args[1].endswith("/gizmos/proj-1/conversations")
    assert calls[2].args[1].endswith("/conversation/conv-1")

def test_project_conversation_cursor_pagination():
    client = ChatGPTClient(access_token="token-value", account_id="acct-value")
    mock = MagicMock()
    mock.request.side_effect = [
        MagicMock(status_code=200, ok=True, json=lambda: {
            "items": [{"id": "c1"}],
            "cursor": "next-cursor",
        }),
        MagicMock(status_code=200, ok=True, json=lambda: {
            "items": [{"id": "c2"}],
            "cursor": None,
        }),
    ]
    client.session = mock

    result = client.list_conversations(project_id="proj-1", limit=50)
    assert [x["id"] for x in result["items"]] == ["c1", "c2"]
    assert mock.request.call_args_list[1].kwargs["params"]["cursor"] == "next-cursor"
