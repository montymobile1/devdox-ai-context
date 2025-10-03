import pytest
from unittest.mock import MagicMock, patch
from app.core.exceptions.base_exceptions import DevDoxAPIException
from app.core.config import GitHosting
from app.core.exceptions import exception_constants
from app.infrastructure.external_apis.git_clients import GitClientFactory, retrieve_git_fetcher_or_die


class DummyFetcher:
    pass

class DummyDataMapper:
    pass

@pytest.fixture
def fake_store():
    class FakeStore:
        def get_components(self, provider):
            if provider == GitHosting.GITHUB:
                return DummyFetcher(), DummyDataMapper()
            if provider == GitHosting.GITLAB:
                return DummyFetcher(), DummyDataMapper()
            if provider == "nodatamapper":
                return DummyFetcher(), None
            if provider == "nofetcher":
                return None, DummyDataMapper()
            return None, None

    return FakeStore()

# --- Tests for retrieve_git_fetcher_or_die ---

def test_retrieve_git_fetcher_or_die_success(fake_store):
    fetcher, mapper = retrieve_git_fetcher_or_die(fake_store, GitHosting.GITHUB)
    assert isinstance(fetcher, DummyFetcher)
    assert isinstance(mapper, DummyDataMapper)

def test_retrieve_git_fetcher_or_die_no_fetcher(fake_store):
    with pytest.raises(DevDoxAPIException) as exc:
        retrieve_git_fetcher_or_die(fake_store, "nofetcher")
    assert exception_constants.SERVICE_UNAVAILABLE in str(exc.value.user_message)

def test_retrieve_git_fetcher_or_die_no_data_mapper(fake_store):
    with pytest.raises(DevDoxAPIException) as exc:
        retrieve_git_fetcher_or_die(fake_store, "nodatamapper")
    assert exception_constants.SERVICE_UNAVAILABLE in str(exc.value.user_message)

def test_retrieve_git_fetcher_or_die_data_mapper_not_required(fake_store):
    fetcher, mapper = retrieve_git_fetcher_or_die(fake_store, "nodatamapper", include_data_mapper=False)
    assert isinstance(fetcher, DummyFetcher)
    assert mapper is None

# --- Tests for GitClientFactory ---

def test_create_client_github(fake_store):
    factory = GitClientFactory(fake_store)
    with patch("devdox_ai_git.git_managers.GitHubManager.authenticate") as mock_auth:
        mock_auth.return_value = "github_client"
        client = factory.create_client("github", token="gh-token")
        assert client == "github_client"
        mock_auth.assert_called_once_with(access_token="gh-token")

def test_create_client_gitlab(fake_store):
    factory = GitClientFactory(fake_store)
    with patch("devdox_ai_git.git_managers.GitLabManager.authenticate") as mock_auth:
        mock_auth.return_value = "gitlab_client"
        client = factory.create_client("gitlab", token="gl-token")
        assert client == "gitlab_client"
        mock_auth.assert_called_once_with(access_token="gl-token")

def test_create_client_invalid_string_provider(fake_store):
    factory = GitClientFactory(fake_store)
    with pytest.raises(DevDoxAPIException) as exc:
        factory.create_client("bitbucket", token="xxx")
    assert "Bitbucket" in str(exc.value.log_message) or "bitbucket" in str(exc.value.log_message)

def test_create_client_enum_provider(fake_store):
    factory = GitClientFactory(fake_store)
    with patch("devdox_ai_git.git_managers.GitHubManager.authenticate") as mock_auth:
        mock_auth.return_value = "enum_client"
        client = factory.create_client(GitHosting.GITHUB, token="xxx")
        assert client == "enum_client"

def test_create_client_fallback_error(fake_store):
    factory = GitClientFactory(fake_store)
    # FakeStore returns valid fetcher, but unsupported provider format will skip logic
    with pytest.raises(DevDoxAPIException) as exc:
        factory.create_client("unsupported-provider", token="123")
    assert exception_constants.SERVICE_UNAVAILABLE in str(exc.value.user_message)

def test_create_client_wraps_generic_exception(fake_store):
    factory = GitClientFactory(fake_store)
    # Inject failure into fetcher retrieval
    factory.store.get_components = MagicMock(side_effect=Exception("boom"))

    with pytest.raises(DevDoxAPIException) as exc:
        factory.create_client("github", token="xx")
    assert "boom" in str(exc.value.__cause__)
    assert "provider" in str(exc.value.internal_context)
