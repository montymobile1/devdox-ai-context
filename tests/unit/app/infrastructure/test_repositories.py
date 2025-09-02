import datetime
import logging
import uuid

import pytest
from _pytest.logging import LogCaptureFixture
from models_src.test_doubles.repositories.git_label import StubGitLabelStore

from app.core.exceptions.local_exceptions import ContextNotFoundError, RepoNotFoundError
from models_src.test_doubles.repositories.api_key import FakeApiKeyStore
from models_src.test_doubles.repositories.repo import FakeRepoStore, StubRepoStore

from app.core.exceptions import exception_constants

from app.infrastructure.database.repositories import APIKeyRepositoryHelper, ContextRepositoryHelper, \
	GitLabelRepositoryHelper, \
	RepoRepositoryHelper, UserRepositoryHelper
from models_src.dto.user import UserResponseDTO
from models_src.test_doubles.repositories.user import FakeUserStore, StubUserStore

from app.core.config import GitHosting


@pytest.mark.asyncio
class TestUserRepositoryHelper:
	
	async def test_find_by_user_id_returns_value(self) -> None:
		
		user_repository = FakeUserStore()
		
		user_id_2 = uuid.uuid4()
		
		user_repository.set_fake_data([
			UserResponseDTO(user_id=str(uuid.uuid4())),
			UserResponseDTO(user_id=str(user_id_2)),
			UserResponseDTO(user_id=str(uuid.uuid4()))
		])
		
		helper = UserRepositoryHelper(repo=user_repository)
		
		returned_value = await helper.find_by_user_id(user_id=str(user_id_2))
		
		assert returned_value
	
	async def test_find_by_user_id_returns_nothing(self) -> None:
		"""
		Tests method where it cant find a valid value
		"""
		user_repository = FakeUserStore()
		
		user_repository.set_fake_data([
			UserResponseDTO(user_id=str(uuid.uuid4())),
			UserResponseDTO(user_id=str(uuid.uuid4()))
		])
		
		helper = UserRepositoryHelper(repo=user_repository)
		
		returned_value = await helper.find_by_user_id(user_id=str(uuid.uuid4()))
		
		assert not returned_value
	
	async def test_find_by_user_id_returns_exception(self, caplog:LogCaptureFixture) -> None:
		"""
		Tests method where it returns an exception
		"""
		user_repository = FakeUserStore()
		
		user_repository.set_exception(user_repository.find_by_user_id, Exception("Exception Occurred :)"))
		
		helper = UserRepositoryHelper(repo=user_repository)
		
		user_id = uuid.uuid4()
		
		with caplog.at_level(logging.INFO):
			returned_value = await helper.find_by_user_id(user_id=str(user_id))
		
		assert not returned_value
		assert any(
		        r.message == exception_constants.ERROR_USER_NOT_FOUND_BY_ID.format(user_id=str(user_id))
		        for r in caplog.records
		    )
	
	@pytest.mark.parametrize(
		"db_output", [-1, 0], ids=["invalid inputs", "no data"]
	)
	async def test_update_token_usage_updates_nothing(self, db_output) -> None:
		user_repository = StubUserStore()
		
		user_repository.set_output(user_repository.increment_token_usage, db_output)
		
		helper = UserRepositoryHelper(repo=user_repository)
		
		with pytest.raises(Exception) as exc_info:
			_ = await helper.update_token_usage(user_id=str(uuid.uuid4()), tokens_used=1)
		
		assert exc_info.value.user_message == exception_constants.DB_USER_TOKEN_UPDATE_FAILED
	

	async def test_create_user_has_exception(self) -> None:
		user_repository = StubUserStore()
		
		user_repository.set_exception(user_repository.increment_token_usage, Exception("EXCEPTION OCCURRED"))
		
		helper = UserRepositoryHelper(repo=user_repository)
		
		with pytest.raises(Exception) as exc_info:
			_ = await helper.create_user(user_data={})
		
		assert exc_info.value.user_message == exception_constants.DB_USER_CREATION_FAILED

@pytest.mark.asyncio
class TestAPIKeyRepositoryHelper:
	
	async def test_find_active_by_key_has_exception(self, caplog:LogCaptureFixture) -> None:
		
		repository = FakeApiKeyStore()
		
		repository.set_exception(repository.find_by_active_api_key, Exception("EXCEPTION OCCURRED"))
		
		helper = APIKeyRepositoryHelper(repo=repository)
		
		with caplog.at_level(logging.INFO):
			returned_value = await helper.find_active_by_key(api_key=str(uuid.uuid4()))
			
		assert not returned_value
		assert any(
			r.message == exception_constants.ERROR_FINDING_API_KEY
			for r in caplog.records
		)
		
	async def test_update_last_used_has_exception(self) -> None:
		
		repository = FakeApiKeyStore()
		
		repository.set_exception(repository.update_last_used_by_id, Exception("EXCEPTION OCCURRED"))
		
		helper = APIKeyRepositoryHelper(repo=repository)
		
		with pytest.raises(Exception) as exc_info:
			await helper.update_last_used(api_key_id=str(uuid.uuid4()))
		
		assert exc_info.value.user_message == exception_constants.DB_API_KEY_UPDATE_FAILED

@pytest.mark.asyncio
class TestRepoRepositoryHelper:
	
	async def test_find_by_repo_id_has_exception(self, caplog:LogCaptureFixture) -> None:
		
		repository = FakeRepoStore()
		
		repository.set_exception(repository.find_by_repo_id, Exception("EXCEPTION OCCURRED"))
		
		helper = RepoRepositoryHelper(repo=repository)
		
		repo_id = str(uuid.uuid4())
		
		with caplog.at_level(logging.INFO):
			returned_value = await helper.find_by_repo_id(repo_id=repo_id)
			
		assert not returned_value
		assert any(
			r.message == exception_constants.ERROR_REPO_NOT_FOUND_BY_REPO_ID.format(repo_id=repo_id)
			for r in caplog.records
		)
		
	async def test_find_by_user_and_url_has_exception(self, caplog:LogCaptureFixture) -> None:
		
		repository = FakeRepoStore()
		
		repository.set_exception(repository.find_by_user_id_and_html_url, Exception("EXCEPTION OCCURRED"))
		
		helper = RepoRepositoryHelper(repo=repository)
		
		user_id = str(uuid.uuid4())
		html_url = "some html url"
		
		
		
		with caplog.at_level(logging.INFO):
			returned_value = await helper.find_by_user_and_url(user_id=user_id, html_url=html_url)
		
		assert not returned_value
		assert any(
			r.message == exception_constants.ERROR_FINDING_REPO.format(user_id=user_id, html_url=html_url)
			for r in caplog.records
		)
		
		
@pytest.mark.asyncio
class TestGitLabelRepositoryHelper:
	
	async def test_find_by_user_and_hosting_has_exception(self, caplog:LogCaptureFixture) -> None:
		"""
		Tests method where it returns an exception
		"""
		repository = StubGitLabelStore()
		
		repository.set_exception(repository.find_by_id_and_user_id_and_git_hosting, Exception("Exception Occurred :)"))
		
		helper = GitLabelRepositoryHelper(repo=repository)
		
		with caplog.at_level(logging.INFO):
			returned_value = await helper.find_by_user_and_hosting(user_id="u1", id=str(uuid.uuid4()), git_hosting=GitHosting.GITHUB.value)
		
		
		assert not returned_value
		assert any(
			r.message == exception_constants.ERROR_FINDING_GIT_LABEL
			for r in caplog.records
		)

@pytest.mark.asyncio
class TestContextRepositoryHelper:
	
	async def test_create_context_has_exception(self):
		"""
		Tests method where it returns an exception
		"""
		repository = StubRepoStore()
		
		repository.set_exception(repository.save_context, Exception("Exception Occurred :)"))
		
		helper = ContextRepositoryHelper(repo=repository)
		
		with pytest.raises(Exception) as exc_info:
			_ = await helper.create_context(
				repo_id=str(uuid.uuid4()), user_id=str(uuid.uuid4()), config={}
			)
			
		assert exc_info.value.user_message == exception_constants.DB_CONTEXT_REPO_CREATE_FAILED
	
	@pytest.mark.parametrize(
		"db_output", [-1, 0], ids=["invalid inputs", "no data"]
	)
	async def test_update_status_has_exception_1(self, db_output) -> None:
		"""Returns RepoNotFoundError"""
		
		user_repository = StubRepoStore()
		
		user_repository.set_output(user_repository.update_analysis_metadata_by_id, db_output)
		
		helper = ContextRepositoryHelper(repo=user_repository)
		
		with pytest.raises(ContextNotFoundError) as exc_info:
			_ = await helper.update_status(context_id=str(uuid.uuid4()), status="some status",processing_end_time=datetime.datetime.now(datetime.timezone.utc),
                total_files=0,
                total_chunks=0,
                total_embeddings=0,)

		assert exc_info.value.user_message == exception_constants.CONTEXT_NOT_FOUND
	
	async def test_update_status_has_exception_2(self) -> None:
		"""Returns RepoNotFoundError"""
		
		user_repository = StubRepoStore()
		
		user_repository.set_exception(user_repository.update_analysis_metadata_by_id, Exception("EXCEPTION OCCURRED"))
		
		helper = ContextRepositoryHelper(repo=user_repository)
		
		with pytest.raises(Exception) as exc_info:
			_ = await helper.update_status(context_id=str(uuid.uuid4()), status="some status", processing_end_time=datetime.datetime.now(datetime.timezone.utc),
											total_files=0,
											total_chunks=0,
											total_embeddings=0
			                               )
		
		assert exc_info.value.user_message == exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED
	
	@pytest.mark.parametrize(
		"db_output", [-1, 0], ids=["invalid inputs", "no data"]
	)
	async def test_update_repo_repo_system_reference_has_exception_1(self, db_output) -> None:
		"""Returns RepoNotFoundError"""
		
		user_repository = StubRepoStore()
		
		user_repository.set_output(user_repository.update_repo_system_reference_by_id, db_output)
		
		helper = ContextRepositoryHelper(repo=user_repository)
		
		with pytest.raises(ContextNotFoundError) as exc_info:
			_ = await helper.update_repo_system_reference(context_id=str(uuid.uuid4()), repo_system_reference="some repo_system_reference")
		
		assert exc_info.value.user_message == exception_constants.CONTEXT_NOT_FOUND
	
	async def test_update_repo_repo_system_reference_has_exception_2(self) -> None:
		"""Returns RepoNotFoundError"""
		
		user_repository = StubRepoStore()
		
		user_repository.set_exception(user_repository.update_repo_system_reference_by_id, Exception("EXCEPTION OCCURRED"))
		
		helper = ContextRepositoryHelper(repo=user_repository)
		
		with pytest.raises(Exception) as exc_info:
			_ = await helper.update_repo_system_reference(context_id=str(uuid.uuid4()), repo_system_reference="some repo_system_reference")
		
		assert exc_info.value.user_message == exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED
	