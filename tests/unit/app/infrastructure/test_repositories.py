import datetime
import logging
import uuid

import pytest
from _pytest.logging import LogCaptureFixture

from app.core.exceptions.local_exceptions import (
    ContextNotFoundError,
    DatabaseError,
    RepoNotFoundError,
)

from app.core.exceptions import exception_constants

from app.infrastructure.database.repositories import (
    APIKeyRepositoryHelper,
    CodeChunksRepositoryHelper,
    ContextRepositoryHelper,
    GitLabelRepositoryHelper,
    RepoRepositoryHelper,
    UserRepositoryHelper,
)

from models_src import (
    EMBED_DIM,
    APIKeyResponseDTO,
    GenericFakeStore, GenericStubStore, InMemoryApiKeyBackend, InMemoryCodeChunksBackend,
    InMemoryGitLabelBackend, InMemoryRepoBackend, InMemoryUserBackend, RepoResponseDTO,
    CodeChunksRequestDTO,
    CodeChunksResponseDTO,
    UserResponseDTO, make_fake_git_label, make_fake_user
)

from app.core.config import GitHosting

@pytest.mark.asyncio
class TestUserRepositoryHelper:
    
    InMemoUser = InMemoryUserBackend
    
    async def test_find_by_user_id_returns_value(self) -> None:
        
        # ARRANGE
        
        user_repository = GenericFakeStore(in_memory_backend=self.InMemoUser())
        
        user_id_2 = uuid.uuid4()
        
        user_repository.backend.set_data_store(
            [
                UserResponseDTO(user_id=str(uuid.uuid4())),
                UserResponseDTO(user_id=str(user_id_2)),
                UserResponseDTO(user_id=str(uuid.uuid4())),
            ]
        )
        
        

        # ACT
        helper = UserRepositoryHelper(repo=user_repository)
        returned_value = await helper.find_by_user_id(user_id=str(user_id_2))
        
        # ASSERT
        assert returned_value

    async def test_find_by_user_id_returns_nothing(self) -> None:
        """
        Tests method where it cant find a valid value
        """
        # ARRANGE
        user_repository = GenericFakeStore(
            in_memory_backend=self.InMemoUser()
        )
        
        user_repository.backend.set_data_store(
            [
                UserResponseDTO(user_id=str(uuid.uuid4())),
                UserResponseDTO(user_id=str(uuid.uuid4())),
            ]
        )
        
        # ACT
        helper = UserRepositoryHelper(repo=user_repository)
        returned_value = await helper.find_by_user_id(user_id=str(uuid.uuid4()))
        
        # ASSERT
        assert not returned_value

    async def test_find_by_user_id_returns_exception(
        self, caplog: LogCaptureFixture
    ) -> None:
        """
        Tests method where it returns an exception
        """
        
        # ARRANGE
        user_repository = GenericFakeStore(
            in_memory_backend=self.InMemoUser()
        )
        user_repository.set_exception(
            user_repository.store.find_by_user_id, Exception("Exception Occurred :)")
        )
        
        # ACT
        helper = UserRepositoryHelper(repo=user_repository)
        user_id = uuid.uuid4()
        with caplog.at_level(logging.INFO):
            returned_value = await helper.find_by_user_id(user_id=str(user_id))
        
        # ASSERT
        assert not returned_value
        assert any(
            r.message
            == exception_constants.ERROR_USER_NOT_FOUND_BY_ID.format(
                user_id=str(user_id)
            )
            for r in caplog.records
        )

    @pytest.mark.parametrize("db_output", [-1, 0], ids=["invalid inputs", "no data"])
    async def test_update_token_usage_updates_nothing(self, db_output) -> None:
        user_repository = GenericStubStore()

        user_repository.set_output(InMemoryUserBackend.increment_token_usage, db_output)

        helper = UserRepositoryHelper(repo=user_repository)

        with pytest.raises(Exception) as exc_info:
            _ = await helper.update_token_usage(
                user_id=str(uuid.uuid4()), tokens_used=1
            )

        assert (
            exc_info.value.user_message
            == exception_constants.DB_USER_TOKEN_UPDATE_FAILED
        )

    async def test_create_user_has_exception(self) -> None:
        user_repository = GenericStubStore()

        user_repository.set_exception(
            InMemoryUserBackend.increment_token_usage, Exception("EXCEPTION OCCURRED")
        )

        helper = UserRepositoryHelper(repo=user_repository)

        with pytest.raises(Exception) as exc_info:
            _ = await helper.create_user(user_data={})

        assert (
            exc_info.value.user_message == exception_constants.DB_USER_CREATION_FAILED
        )

    async def test_find_by_user_id_ok(self):
        stub = GenericStubStore()
        user = make_fake_user(user_id="u-1")
        stub.set_output(InMemoryUserBackend.find_by_user_id, user)
        helper = UserRepositoryHelper(repo=stub)

        got = await helper.find_by_user_id("u-1")
        assert got is user

    async def test_find_by_user_id_logs_and_returns_none_on_exception(self, caplog):
        stub = GenericStubStore()
        stub.set_exception(InMemoryUserBackend.find_by_user_id, RuntimeError("boom"))
        helper = UserRepositoryHelper(repo=stub)

        with caplog.at_level(logging.ERROR):
            got = await helper.find_by_user_id("u-404")
        assert got is None
        assert (
            exception_constants.ERROR_USER_NOT_FOUND_BY_ID.split("{")[0] in caplog.text
        )

    async def test_update_token_usage_ok(self, caplog):
        stub = GenericStubStore()
        stub.set_output(InMemoryUserBackend.increment_token_usage, 1)
        helper = UserRepositoryHelper(repo=stub)

        with caplog.at_level(logging.INFO):
            await helper.update_token_usage("u-1", 123)
        assert "Updated token usage" in caplog.text

    async def test_update_token_usage_less_than_or_equal_0_raises_database_error(self):
        stub = GenericStubStore()
        stub.set_output(InMemoryUserBackend.increment_token_usage, 0)
        helper = UserRepositoryHelper(repo=stub)

        with pytest.raises(DatabaseError):
            await helper.update_token_usage("u-1", 10)

    async def test_update_token_usage_exception_wrapped(self):
        stub = GenericStubStore()
        stub.set_exception(InMemoryUserBackend.increment_token_usage, RuntimeError("db down"))
        helper = UserRepositoryHelper(repo=stub)

        with pytest.raises(DatabaseError) as ei:
            await helper.update_token_usage("u-1", 10)
        assert exception_constants.DB_USER_TOKEN_UPDATE_FAILED in str(
            ei.value.user_message
        )

    async def test_create_user_ok(self, caplog):
        stub = GenericStubStore()
        returned = make_fake_user(user_id="u-2", email="x@y.com", encryption_salt="s")
        stub.set_output(InMemoryUserBackend.save, returned)
        helper = UserRepositoryHelper(repo=stub)

        payload = {
            "user_id": "u-2",
            "email": "x@y.com",
            "encryption_salt": "s",
            "first_name": "X",
            "last_name": "Y",
            "role": "user",  # or Role.USER
        }

        with caplog.at_level(logging.INFO):
            got = await helper.create_user(payload)

        assert got is returned
        assert "Created new user: u-2" in caplog.text

    async def test_create_user_exception_wrapped(self):
        stub = GenericStubStore()
        stub.set_exception(InMemoryUserBackend.save, RuntimeError("write fail"))
        helper = UserRepositoryHelper(repo=stub)

        with pytest.raises(DatabaseError) as ei:
            await helper.create_user(
                {"user_id": "u", "email": "a@b.c", "encryption_salt": "s"}
            )
        assert exception_constants.DB_USER_CREATION_FAILED in str(ei.value.user_message)


@pytest.mark.asyncio
class TestAPIKeyRepositoryHelper:
    
    InMemo = InMemoryApiKeyBackend
    
    async def test_find_active_by_key_has_exception(
        self, caplog: LogCaptureFixture
    ) -> None:
        
        repository = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )
        
        repository.set_exception(
            InMemoryApiKeyBackend.find_by_active_api_key, Exception("EXCEPTION OCCURRED")
        )

        helper = APIKeyRepositoryHelper(repo=repository)

        with caplog.at_level(logging.INFO):
            returned_value = await helper.find_active_by_key(api_key=str(uuid.uuid4()))

        assert not returned_value
        assert any(
            r.message == exception_constants.ERROR_FINDING_API_KEY
            for r in caplog.records
        )

    async def test_update_last_used_has_exception(self) -> None:
        
        repository = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )

        repository.set_exception(
            InMemoryApiKeyBackend.update_last_used_by_id, Exception("EXCEPTION OCCURRED")
        )

        helper = APIKeyRepositoryHelper(repo=repository)

        with pytest.raises(Exception) as exc_info:
            await helper.update_last_used(api_key_id=str(uuid.uuid4()))

        assert (
            exc_info.value.user_message == exception_constants.DB_API_KEY_UPDATE_FAILED
        )

    async def test_find_active_by_key_ok(self):
        stub = GenericStubStore()
        obj = APIKeyResponseDTO(
            id=uuid.uuid4(), user_id="u", api_key="k", is_active=True
        )
        stub.set_output(InMemoryApiKeyBackend.find_by_active_api_key, obj)
        helper = APIKeyRepositoryHelper(repo=stub)

        got = await helper.find_active_by_key("k")
        assert got is obj

    async def test_find_active_by_key_logs_and_returns_none_on_exception(self, caplog):
        stub = GenericStubStore()
        stub.set_exception(InMemoryApiKeyBackend.find_by_active_api_key, RuntimeError("x"))
        helper = APIKeyRepositoryHelper(repo=stub)

        with caplog.at_level(logging.ERROR):
            got = await helper.find_active_by_key("k")
        assert got is None
        assert exception_constants.ERROR_FINDING_API_KEY in caplog.text

    async def test_update_last_used_ok(self):
        stub = GenericStubStore()
        stub.set_output(InMemoryApiKeyBackend.update_last_used_by_id, 1)
        helper = APIKeyRepositoryHelper(repo=stub)
        await helper.update_last_used("some-id")  # no exception

    async def test_update_last_used_wraps_exception(self):
        stub = GenericStubStore()
        stub.set_exception(InMemoryApiKeyBackend.update_last_used_by_id, RuntimeError("fail"))
        helper = APIKeyRepositoryHelper(repo=stub)
        with pytest.raises(DatabaseError) as ei:
            await helper.update_last_used("x")
        assert exception_constants.DB_API_KEY_UPDATE_FAILED in str(
            ei.value.user_message
        )


@pytest.mark.asyncio
class TestRepoRepositoryHelper:
    
    InMemo = InMemoryRepoBackend
    FakeStore = InMemoryRepoBackend
    
    async def test_find_by_repo_id_has_exception(
        self, caplog: LogCaptureFixture
    ) -> None:
        
        repository = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )
        
        repository.set_exception(
            self.FakeStore.find_by_repo_id, Exception("EXCEPTION OCCURRED")
        )
        repository.set_exception(
            self.FakeStore.find_by_repo_id_user_id, Exception("EXCEPTION OCCURRED")
        )

        helper = RepoRepositoryHelper(repo=repository)

        repo_id = str(uuid.uuid4())

        with caplog.at_level(logging.INFO):
            returned_value = await helper.find_by_repo_id(repo_id=repo_id)

        assert not returned_value
        assert any(
            r.message
            == exception_constants.ERROR_REPO_NOT_FOUND_BY_REPO_ID.format(
                repo_id=repo_id
            )
            for r in caplog.records
        )

    async def test_find_by_user_and_url_has_exception(
        self, caplog: LogCaptureFixture
    ) -> None:
        
        repository = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )
        
        repository.set_exception(
            self.FakeStore.find_by_user_id_and_html_url, Exception("EXCEPTION OCCURRED")
        )

        helper = RepoRepositoryHelper(repo=repository)

        user_id = str(uuid.uuid4())
        html_url = "some html url"

        with caplog.at_level(logging.INFO):
            returned_value = await helper.find_by_user_and_url(
                user_id=user_id, html_url=html_url
            )

        assert not returned_value
        assert any(
            r.message
            == exception_constants.ERROR_FINDING_REPO.format(
                user_id=user_id, html_url=html_url
            )
            for r in caplog.records
        )

    async def test_find_by_repo_id_ok(self):
        stub = GenericStubStore()
        repo = RepoResponseDTO(id=uuid.uuid4(), repo_id="r-1", user_id="u")
        stub.set_output(self.FakeStore.find_by_repo_id, repo)
        helper = RepoRepositoryHelper(repo=stub)
        got = await helper.find_by_repo_id("r-1")
        assert got is repo

    async def test_find_by_repo_id_logs_none_on_exception(self, caplog):
        stub = GenericStubStore()
        stub.set_exception(self.FakeStore.find_by_repo_id, RuntimeError())
        helper = RepoRepositoryHelper(repo=stub)
        with caplog.at_level(logging.ERROR):
            got = await helper.find_by_repo_id("r-404")
        assert got is None
        assert (
            exception_constants.ERROR_REPO_NOT_FOUND_BY_REPO_ID.split("{")[0]
            in caplog.text
        )

    async def test_find_repo_by_id_ok_and_logs_on_exception(self, caplog):
        stub = GenericStubStore()
        repo = RepoResponseDTO(id=uuid.uuid4(), repo_id="r2", user_id="u")
        stub.set_output(self.FakeStore.find_by_id, repo)
        helper = RepoRepositoryHelper(repo=stub)
        assert await helper.find_repo_by_id("abc") is repo

        stub.set_exception(self.FakeStore.find_by_id, RuntimeError())
        with caplog.at_level(logging.ERROR):
            assert await helper.find_repo_by_id("nope") is None
        assert (
            exception_constants.ERROR_REPO_NOT_FOUND_BY_ID.split("{")[0] in caplog.text
        )

    async def test_find_by_user_and_url_ok_and_logs_on_exception(self, caplog):
        stub = GenericStubStore()
        repo = RepoResponseDTO(
            id=uuid.uuid4(), repo_id="r3", user_id="u", html_url="https://x"
        )
        stub.set_output(self.FakeStore.find_by_user_id_and_html_url, repo)
        helper = RepoRepositoryHelper(repo=stub)
        assert await helper.find_by_user_and_url("u", "https://x") is repo

        stub.set_exception(self.FakeStore.find_by_user_id_and_html_url, RuntimeError())
        with caplog.at_level(logging.ERROR):
            assert await helper.find_by_user_and_url("u", "no") is None
        assert exception_constants.ERROR_FINDING_REPO.split("{")[0] in caplog.text


@pytest.mark.asyncio
class TestGitLabelRepositoryHelper:
    
    FakeStore = InMemoryGitLabelBackend
    
    async def test_find_by_user_and_hosting_has_exception(
        self, caplog: LogCaptureFixture
    ) -> None:
        """
        Tests method where it returns an exception
        """
        repository = GenericStubStore()

        repository.set_exception(
            self.FakeStore.find_by_id_and_user_id_and_git_hosting,
            Exception("Exception Occurred :)"),
        )

        helper = GitLabelRepositoryHelper(repo=repository)

        with caplog.at_level(logging.INFO):
            returned_value = await helper.find_by_user_and_hosting(
                user_id="u1", id=str(uuid.uuid4()), git_hosting=GitHosting.GITHUB.value
            )

        assert not returned_value
        assert any(
            r.message == exception_constants.ERROR_FINDING_GIT_LABEL
            for r in caplog.records
        )

    async def test_find_by_user_and_hosting_ok(self):
        stub = GenericStubStore()
        label = make_fake_git_label(git_hosting="github")
        stub.set_output(self.FakeStore.find_by_id_and_user_id_and_git_hosting, label)
        helper = GitLabelRepositoryHelper(repo=stub)
        got = await helper.find_by_user_and_hosting("u", str(label.id), "github")
        assert got is label

    async def test_find_by_user_and_hosting_logs_and_returns_none(self, caplog):
        stub = GenericStubStore()
        stub.set_exception(
            self.FakeStore.find_by_id_and_user_id_and_git_hosting, RuntimeError()
        )
        helper = GitLabelRepositoryHelper(repo=stub)
        with caplog.at_level(logging.ERROR):
            got = await helper.find_by_user_and_hosting("u", "id", "github")
        assert got is None
        assert exception_constants.ERROR_FINDING_GIT_LABEL in caplog.text


@pytest.mark.asyncio
class TestContextRepositoryHelper:
    
    InMemo = InMemoryRepoBackend
    
    async def test_create_context_has_exception(self):
        """
        Tests method where it returns an exception
        """
        repository = GenericStubStore()

        repository.set_exception(
            self.InMemo.save_context, Exception("Exception Occurred :)")
        )

        helper = ContextRepositoryHelper(repo=repository)

        with pytest.raises(Exception) as exc_info:
            _ = await helper.create_context(
                repo_id=str(uuid.uuid4()), user_id=str(uuid.uuid4()), config={}
            )

        assert (
            exc_info.value.user_message
            == exception_constants.DB_CONTEXT_REPO_CREATE_FAILED
        )

    @pytest.mark.parametrize("db_output", [-1, 0], ids=["invalid inputs", "no data"])
    async def test_update_status_has_exception_1(self, db_output) -> None:
        """Returns RepoNotFoundError"""

        user_repository = GenericStubStore()
        
        user_repository.set_output(
            self.InMemo.update_analysis_metadata_by_id, db_output
        )

        helper = ContextRepositoryHelper(repo=user_repository)

        with pytest.raises(ContextNotFoundError) as exc_info:
            _ = await helper.update_status(
                context_id=str(uuid.uuid4()),
                status="some status",
                processing_end_time=datetime.datetime.now(datetime.timezone.utc),
                total_files=0,
                total_chunks=0,
                total_embeddings=0,
            )

        assert exc_info.value.user_message == exception_constants.CONTEXT_NOT_FOUND

    async def test_update_status_has_exception_2(self) -> None:
        """Returns RepoNotFoundError"""

        user_repository = GenericStubStore()

        user_repository.set_exception(
            self.InMemo.update_analysis_metadata_by_id,
            Exception("EXCEPTION OCCURRED"),
        )

        helper = ContextRepositoryHelper(repo=user_repository)

        with pytest.raises(Exception) as exc_info:
            _ = await helper.update_status(
                context_id=str(uuid.uuid4()),
                status="some status",
                processing_end_time=datetime.datetime.now(datetime.timezone.utc),
                total_files=0,
                total_chunks=0,
                total_embeddings=0,
            )

        assert (
            exc_info.value.user_message
            == exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED
        )

    @pytest.mark.parametrize("db_output", [-1, 0], ids=["invalid inputs", "no data"])
    async def test_update_repo_repo_system_reference_has_exception_1(
        self, db_output
    ) -> None:
        """Returns RepoNotFoundError"""

        user_repository = GenericStubStore()

        user_repository.set_output(
            self.InMemo.update_repo_system_reference_by_id, db_output
        )

        helper = ContextRepositoryHelper(repo=user_repository)

        with pytest.raises(ContextNotFoundError) as exc_info:
            _ = await helper.update_repo_system_reference(
                context_id=str(uuid.uuid4()),
                repo_system_reference="some repo_system_reference",
            )

        assert exc_info.value.user_message == exception_constants.CONTEXT_NOT_FOUND

    async def test_update_repo_repo_system_reference_has_exception_2(self) -> None:
        """Returns RepoNotFoundError"""

        user_repository = GenericStubStore()

        user_repository.set_exception(
            self.InMemo.update_repo_system_reference_by_id,
            Exception("EXCEPTION OCCURRED"),
        )

        helper = ContextRepositoryHelper(repo=user_repository)

        with pytest.raises(Exception) as exc_info:
            _ = await helper.update_repo_system_reference(
                context_id=str(uuid.uuid4()),
                repo_system_reference="some repo_system_reference",
            )

        assert (
            exc_info.value.user_message
            == exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED
        )

    async def test_create_context_ok(self, caplog):
        # Use FakeRepoStore for stateful behavior
        fake = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )
        
        helper = ContextRepositoryHelper(repo=fake)
        with caplog.at_level(logging.INFO):
            ctx = await helper.create_context("repo1", "u", {"any": "cfg"})
        assert isinstance(ctx, RepoResponseDTO)
        assert ctx.repo_id == "repo1"
        assert "Created context for repo repo1" in caplog.text

    async def test_create_context_wraps_exception(self):
        stub = GenericStubStore()
        stub.set_exception(self.InMemo.save_context, RuntimeError("x"))
        helper = ContextRepositoryHelper(repo=stub)
        with pytest.raises(DatabaseError) as ei:
            await helper.create_context("r", "u", {})
        assert exception_constants.DB_CONTEXT_REPO_CREATE_FAILED in str(
            ei.value.user_message
        )

    async def test_update_status_ok_and_not_found_and_wrapped(self, caplog):
        stub = GenericStubStore()
        helper = ContextRepositoryHelper(repo=stub)

        # OK (repo.update returns >0)
        stub.set_output(self.InMemo.update_analysis_metadata_by_id, 1)
        with caplog.at_level(logging.INFO):
            await helper.update_status(
                "ctx-1", "done", datetime.datetime.now(datetime.timezone.utc), 1, 2, 3
            )
        assert "Updated context ctx-1 status to done" in caplog.text

        # Not found (<=0) -> ContextNotFoundError
        stub.set_output(self.InMemo.update_analysis_metadata_by_id, 0)
        with pytest.raises(ContextNotFoundError):
            await helper.update_status(
                "ctx-404", "x", datetime.datetime.now(datetime.timezone.utc), 0, 0, 0
            )

        # Wrapped generic exception -> DatabaseError
        stub.set_exception(
            self.InMemo.update_analysis_metadata_by_id, RuntimeError("db")
        )
        with pytest.raises(DatabaseError) as ei:
            await helper.update_status(
                "ctx-e", "x", datetime.datetime.now(datetime.timezone.utc), 0, 0, 0
            )
        assert exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED in str(
            ei.value.user_message
        )

    async def test_update_repo_system_reference_ok_and_errors(self, caplog):
        stub = GenericStubStore()
        helper = ContextRepositoryHelper(repo=stub)

        # OK
        stub.set_output(self.InMemo.update_repo_system_reference_by_id, 1)
        with caplog.at_level(logging.INFO):
            await helper.update_repo_system_reference("ctx-1", "ref-123")
        assert "Updated context ctx-1" in caplog.text

        # Not found
        stub.set_output(self.InMemo.update_repo_system_reference_by_id, 0)
        with pytest.raises(ContextNotFoundError):
            await helper.update_repo_system_reference("ctx-404", "ref")

        # Wrapped
        stub.set_exception(
            self.InMemo.update_repo_system_reference_by_id, RuntimeError("x")
        )
        with pytest.raises(DatabaseError) as ei:
            await helper.update_repo_system_reference("ctx-e", "ref")
        assert exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED in str(
            ei.value.user_message
        )


@pytest.mark.asyncio
class TestCodeChunksRepositoryHelper:
    
    InMemo = InMemoryCodeChunksBackend
    FakeStore = InMemoryCodeChunksBackend
    
    async def test_store_embeddings_ok_with_fake(self, caplog):
        fake = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )
        
        helper = CodeChunksRepositoryHelper(repo=fake)

        vec = [0.0] * EMBED_DIM
        data = [
            {
                "content": "hello",
                "embedding": vec,
                "metadata": {"k": "v"},
                "file_name": "readme.md",
                "file_path": "/readme.md",
                "file_size": 5,
            }
        ]

        with caplog.at_level(logging.INFO):
            first = await helper.store_emebeddings(
                "repo1", "u", data, commit_number="c1"
            )
        assert isinstance(first, CodeChunksResponseDTO)
        assert first.repo_id == "repo1"
        assert "Stored 1 embeddings for repo repo1" in caplog.text

    async def test_store_embeddings_wraps_exception(self):
        stub = GenericStubStore()
        stub.set_exception(self.FakeStore.save, RuntimeError("write fail"))
        helper = CodeChunksRepositoryHelper(repo=stub)

        with pytest.raises(DatabaseError) as ei:
            await helper.store_emebeddings("r", "u", [{"content": "x"}], "c")
        assert exception_constants.DB_CODE_CHUNKS_CREATE_FAILED in str(
            ei.value.user_message
        )

    async def test_find_by_repo_ok_and_logs_empty_on_exception(self, caplog):
        
        fake = GenericFakeStore(
            in_memory_backend=self.InMemo()
        )

        helper = CodeChunksRepositoryHelper(repo=fake)

        # Add two rows for repo A and one for B
        await fake.save(
            CodeChunksRequestDTO(
                repo_id="A",
                user_id="u",
                content="a",
                embedding=None,
                metadata={},
                file_name="a",
                file_path="/a",
                file_size=1,
                commit_number="c",
            )
        )
        await fake.save(
            CodeChunksRequestDTO(
                repo_id="A",
                user_id="u",
                content="b",
                embedding=None,
                metadata={},
                file_name="b",
                file_path="/b",
                file_size=1,
                commit_number="c",
            )
        )
        await fake.save(
            CodeChunksRequestDTO(
                repo_id="B",
                user_id="u",
                content="c",
                embedding=None,
                metadata={},
                file_name="c",
                file_path="/c",
                file_size=1,
                commit_number="c",
            )
        )

        rows = await helper.find_by_repo("A", limit=1)
        assert len(rows) == 1

        # Exception path returns []
        stub = GenericStubStore()
        stub.set_exception(
            self.FakeStore.find_all_by_repo_id_with_limit, RuntimeError("x")
        )
        helper2 = CodeChunksRepositoryHelper(repo=stub)
        with caplog.at_level(logging.ERROR):
            rows2 = await helper2.find_by_repo("A", 5)
        assert rows2 == []
        assert "Error finding code chunks for repo" in caplog.text
