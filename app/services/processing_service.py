import logging
from pathlib import Path
import shutil
import uuid
from git import Repo
from together import Together
from datetime import datetime, timezone
from langchain_community.document_loaders import GitLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List, Dict, Any, Tuple
from app.infrastructure.database.repositories import (
    TortoiseContextRepository,
    TortoiseUserRepository,
    TortoiseRepoRepository,
    TortoiseGitLabelRepository,
    TortoiseCodeChunks,
)
from app.infrastructure.external_apis.git_clients import GitClientFactory
from app.handlers.utils.repo_fetcher import RepoFetcher
from encryption_src.fernet.service import FernetEncryptionHelper
from app.schemas.processing_result import ProcessingResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(
        self,
        context_repository: TortoiseContextRepository,
        user_info: TortoiseUserRepository,
        repo_repository: TortoiseRepoRepository,
        git_label_repository: TortoiseGitLabelRepository,
        encryption_service: FernetEncryptionHelper,
        code_chunks_repository: TortoiseCodeChunks,
        repo_fetcher_store: RepoFetcher = None,
    ):
        self.context_repository = context_repository
        self.repo_repository = repo_repository
        self.user_info = user_info
        self.git_label_repository = git_label_repository
        self.encryption_service = encryption_service
        self.repo_fetcher_store = repo_fetcher_store or RepoFetcher()
        self.git_client_factory = GitClientFactory(store=self.repo_fetcher_store)
        self.base_dir = Path(settings.BASE_DIR)
        self.code_chunks_repository = code_chunks_repository

    async def prepare_repository(self, repo_name) -> Tuple[Path, str]:
        repo_path = self.base_dir / repo_name

        if repo_path.exists():
            shutil.rmtree(repo_path)

        return repo_path

    async def clone_and_process_repository(
        self, repo_url: str, repo_path: str, branch: str = "main"
    ):
        # Clone repository using LangChain's GitLoader
        try:
            loader = GitLoader(
                clone_url=repo_url,
                branch=branch,
                file_filter=lambda file_path: file_path.endswith(
                    (".py", ".js", ".java", ".cpp", ".h", ".cs", ".ts", ".go")
                ),
                repo_path=repo_path,
            )

            documents = loader.load()

            return documents
        except Exception:
            return []

    async def process_repository(self, job_payload: Dict[str, Any]) -> ProcessingResult:
        """Process a repository and create context"""

        context_id = job_payload["context_id"]

        start_time = datetime.now(timezone.utc)

        try:
            # Get repository information
            repo = await self.repo_repository.find_by_repo_id(job_payload["repo_id"])
            if not repo:
                return ProcessingResult(
                    success=False,
                    context_id=context_id,
                    processing_time=0,
                    chunks_created=0,
                    embeddings_created=0,
                    error_message="Repository not found",
                )

            # Get git credentials
            git_client = await self._get_authenticated_git_client(
                job_payload["user_id"],
                job_payload["git_provider"],
                job_payload["git_token"],
            )
            # Fetch repository files
            relative_path = await self.prepare_repository(repo.repo_name)

            files = await self.clone_and_process_repository(
                repo.html_url, relative_path, job_payload.get("branch", "production")
            )
            repo_local = Repo(relative_path)
            commit_hash = repo_local.head.commit.hexsha
            if repo.last_commit == commit_hash and repo.status == "failed":
                return ProcessingResult(
                    success=False,
                    context_id=context_id,
                    processing_time=0,
                    chunks_created=0,
                    embeddings_created=0,
                    error_message="Repository already processed",
                )
            # Process files into chunks
            chunks = await self._process_files_to_chunks(
                files, context_id, repo.id, repo.user_id
            )
            embeddings = await self._create_embeddings(
                chunks,
                model_api_string="togethercomputer/m2-bert-80M-32k-retrieval",
            )

            # Store in vector database
            _ = await self.code_chunks_repository.store_emebeddings(
                repo_id=repo.id,
                user_id=repo.user_id,
                data=embeddings,
                commit_number=commit_hash,
            )
            # Update context completion
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            await self.context_repository.update_status(
                str(repo.id),
                "completed",
                processing_end_time=end_time,
                total_files=len(files),
                total_chunks=len(chunks),
                total_embeddings=len(embeddings),
            )
            return ProcessingResult(
                success=True,
                context_id=context_id,
                processing_time=processing_time,
                chunks_created=len(chunks),
                embeddings_created=len(embeddings),
            )

        except Exception as e:
            logger.error(f"Processing failed for context {context_id}: {str(e)}")

            await self.context_repository.update_status(
                str(job_payload["repo_id"]),
                "failed",
                processing_end_time=datetime.now(timezone.utc),
                total_files=0,
                total_chunks=0,
                total_embeddings=0,
            )

            return ProcessingResult(
                success=False, context_id=context_id, error_message=str(e)
            )

    async def _get_authenticated_git_client(
        self, user_id: str, git_provider: str, git_token: str
    ):
        """Get authenticated git client for user"""

        # Get user's git configuration
        git_config = await self.git_label_repository.find_by_user_and_hosting(
            user_id, git_token, git_provider
        )
        # TODO : check if needed
        # if not git_config:
        #     raise Exception(f"No {git_provider} configuration found for user")

        # Decrypt the stored token
        user = await self.user_info.find_by_user_id(user_id)
        decrypted_token = self.encryption_service.decrypt_for_user(
            git_config.token_value, user.encryption_salt
        )

        # Create git client
        test = self.git_client_factory.create_client(git_provider, decrypted_token)
        return test

    async def _process_files_to_chunks(
        self, files: List[Dict], context_id: str, repo_id: str, user_id: str
    ) -> List[Dict]:
        """Process files into code chunks"""
        chunks = []
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=700, chunk_overlap=200
        )
        chunks = text_splitter.split_documents(files)
        return chunks

    async def _chunk_file_content(self, file_data: Dict, context_id: str) -> List[Dict]:
        """Chunk individual file content"""
        # Implementation for intelligent code chunking
        # This would involve:
        # 1. Language detection
        # 2. AST parsing for semantic boundaries
        # 3. Function/class level chunking
        # 4. Handling imports and dependencies

        chunks = []
        content = file_data["content"]
        file_path = file_data["path"]

        # Simple line-based chunking for now
        lines = content.split("\n")
        chunk_size = 100  # lines per chunk
        overlap = 10

        for i in range(0, len(lines), chunk_size - overlap):
            chunk_lines = lines[i : i + chunk_size]
            chunk_content = "\n".join(chunk_lines)

            if chunk_content.strip():
                chunk = {
                    "context_id": context_id,
                    "content": chunk_content,
                    "file_path": file_path,
                    "start_line": i + 1,
                    "end_line": min(i + chunk_size, len(lines)),
                    "language": self._detect_language(file_path),
                    "chunk_type": "code_block",
                }
                chunks.append(chunk)

        return chunks

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension"""
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "cpp",
            ".hpp": "cpp",
            ".h": "cpp",
        }

        for ext, lang in extension_map.items():
            if file_path.endswith(ext):
                return lang

        return "text"

    async def _create_embeddings(
        self,
        chunks: List[Document],
        model_api_string="togethercomputer/m2-bert-80M-32k-retrieval",
    ) -> List[Dict]:
        """Create vector embeddings for code chunks"""

        embeddings = []
        if len(chunks) > 0:
            together_client = Together(api_key=settings.TOGETHER_API_KEY)

            if chunks:
                # TO DO shoule be changed
                chunk = chunks[0]
                try:
                    response = together_client.embeddings.create(
                        input=chunk.page_content,
                        model=model_api_string,
                    )

                    embedding = {
                        "chunk_id": str(
                            uuid.uuid4()
                        ),  # This would be set after chunk creation
                        "embedding": response.data[0].embedding,
                        "model_name": model_api_string,
                        "model_version": "1.0",
                        "vector_dimension": len(response.data[0].embedding),
                        "content": chunk.page_content,
                        "metadata": chunk.metadata,
                        "file_name": chunk.metadata.get("file_name", ""),
                        "file_path": chunk.metadata.get("file_path", ""),
                        "file_path": chunk.metadata.get("source", ""),
                        "file_size": chunk.metadata.get("file_size", 0),
                    }
                    embeddings.append(embedding)

                except Exception as e:
                    logger.error(f"Failed to create embedding for chunk: {e}")
                    # continue

        return embeddings
