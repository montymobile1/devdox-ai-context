import asyncio
import logging
from pathlib import Path
import shutil
import uuid
from uuid import UUID

from devdox_ai_git.repo_fetcher import RepoFetcher
from git import Repo
from together import Together, AsyncTogether
from datetime import datetime, timezone
from langchain_community.document_loaders import GitLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List, Dict, Any, Optional, Tuple
from app.infrastructure.database.repositories import (
    ContextRepositoryHelper,
    UserRepositoryHelper,
    RepoRepositoryHelper,
    GitLabelRepositoryHelper,
    CodeChunksRepositoryHelper,
)
from app.infrastructure.external_apis.git_clients import GitClientFactory
from encryption_src.fernet.service import FernetEncryptionHelper
from app.schemas.processing_result import ProcessingResult
from app.core.config import settings
from app.infrastructure.job_tracer.job_trace_metadata import JobTraceMetaData
from app.handlers.job_tracker import JobLevels, JobTracker

logger = logging.getLogger(__name__)

package_json_file = "package.json"
package_json_lock_file = "package-lock.json"
yarn_lock_file = "yarn.lock"
build_gradle_file = "build.gradle"
gradle_lockfile_file = "gradle.lockfile"
settings_gradle_file = "settings.gradle"
gradle_properties_file = "gradle.properties"
podfile_lock_file = "Podfile.lock"
podfile_file = "Podfile"

DEPENDENCY_FILES = {
    # Backend Languages
    "Python": [
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-prod.txt",
        "Pipfile",
        "Pipfile.lock",
        "pyproject.toml",
        "poetry.lock",
        "setup.py",
        "setup.cfg",
        "environment.yml",
        "environment.yaml",
        "conda-requirements.txt",
        "pip.conf",
        "pip.ini",
        ".python-version",
    ],
    "nodejs": [
        package_json_file,
        package_json_lock_file,
        yarn_lock_file,
        "pnpm-lock.yaml",
        ".npmrc",
        ".yarnrc",
        ".nvmrc",
    ],
    "Java": [
        "pom.xml",
        build_gradle_file,
        "build.gradle.kts",
        gradle_lockfile_file,
        settings_gradle_file,
        gradle_properties_file,
        "ivy.xml",
        "project.clj",
        "deps.edn",
    ],
    "C#": [
        "*.csproj",
        "*.fsproj",
        "*.vbproj",
        "packages.config",
        "packages.lock.json",
        "Directory.Build.props",
        "Directory.Build.targets",
        "nuget.config",
        "global.json",
        "*.sln",
    ],
    "Go": [
        "go.mod",
        "go.sum",
        "Gopkg.toml",
        "Gopkg.lock",
        "vendor.json",
        "Godeps/Godeps.json",
    ],
    "PHP": ["composer.json", "composer.lock", "composer.phar"],
    "Ruby": [
        "Gemfile",
        "Gemfile.lock",
        "*.gemspec",
        ".ruby-version",
        ".rvmrc",
        "gems.rb",
        "gems.locked",
    ],
    "Rust": ["Cargo.toml", "Cargo.lock", ".cargo/config.toml"],
    "Swift": [
        "Package.swift",
        "Package.resolved",
        podfile_file,
        podfile_lock_file,
        "Cartfile",
        "Cartfile.resolved",
    ],
    "kotlin": [
        build_gradle_file,
        "build.gradle.kts",
        gradle_lockfile_file,
        settings_gradle_file,
        gradle_properties_file,
    ],
    "Scala": [
        "build.sbt",
        "project/build.properties",
        "project/plugins.sbt",
        "project/Dependencies.scala",
    ],
    "Clojure": ["project.clj", "deps.edn", "build.boot"],
    "Erlang": ["rebar.config", "rebar.lock", "mix.exs", "mix.lock"],
    "Elixir": ["mix.exs", "mix.lock"],
    "Dart": ["pubspec.yaml", "pubspec.lock"],
    # Frontend Frameworks
    "JavaScript": [
        package_json_file,
        package_json_lock_file,
        yarn_lock_file,
        "pnpm-lock.yaml",
        ".npmrc",
        ".yarnrc",
        ".nvmrc",
        "bower.json",
        "component.json",
    ],
    "Vue": [
        package_json_file,
        package_json_lock_file,
        yarn_lock_file,
        "vue.config.js",
        "vite.config.js",
        "vite.config.ts",
        ".env",
        ".env.local",
    ],
    # Mobile Platforms
    "Kotlin": [
        build_gradle_file,
        "app/build.gradle",
        gradle_lockfile_file,
        settings_gradle_file,
        gradle_properties_file,
        "gradle/wrapper/gradle-wrapper.properties",
    ],
    "Objective-C": [
        podfile_file,
        podfile_lock_file,
        "Pods",
        "*.xcworkspace",
    ],
    "Objective-C++": [
        podfile_file,
        podfile_lock_file,
        "Pods",
        "*.xcworkspace",
    ],
    "Flutter": ["pubspec.yaml", "pubspec.lock", "analysis_options.yaml"],
}


class ProcessingService:
    def __init__(
        self,
        context_repository: ContextRepositoryHelper,
        user_info: UserRepositoryHelper,
        repo_repository: RepoRepositoryHelper,
        git_label_repository: GitLabelRepositoryHelper,
        encryption_service: FernetEncryptionHelper,
        code_chunks_repository: CodeChunksRepositoryHelper,
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
        self.together_client = Together(api_key=settings.TOGETHER_API_KEY)
        self.readme_files = [
            "README.md",
            "README.txt",
            "README.rst",
            "README",
            "readme.md",
            "readme.txt",
        ]

    def _extract_readme_content(
        self, chunks: List[Document], relative_path: Path
    ) -> Optional[str]:
        """Extract README file content from chunks"""
        for readme_file in self.readme_files:
            for chunk in chunks:
                file_name = chunk.metadata.get("file_name", "").strip()

                if file_name.lower() == readme_file.lower():
                    try:
                        file_path_chunk = relative_path / chunk.metadata.get(
                            "file_path", ""
                        )
                        file_path = Path(file_path_chunk).resolve()

                        if file_path.exists():
                            with file_path.open("r", encoding="utf-8") as f:
                                content = f.read()
                            logger.info(f"Found README file: {file_name}")
                            return content

                    except Exception as e:
                        logger.warning(f"Could not read README file {file_name}: {e}")

        logger.info("No README file found")
        return None

    def _create_readme_analysis_prompt(self, readme_content: str) -> str:
        """Create prompt for README analysis"""
        return f"""Analyze this README file and extract key information in a structured format:

        --- README CONTENT START ---
        {readme_content}
        --- README CONTENT END ---

        Please provide the following structured analysis:

        ## Project Description
        - What does this project do? (1-2 sentences summary)

        ## Key Features
        - Main features and capabilities mentioned

        ## Architecture & Technology Stack
        - Technologies, frameworks, or architectural patterns mentioned
        - Any specific technical requirements or constraints

        ## Setup & Installation
        - Installation steps or requirements mentioned
        - Dependencies or prerequisites

        ## Usage Examples
        - How to use the project (commands, API examples, etc.)

        ## Development Information
        - Development setup instructions
        - Testing information
        - Contribution guidelines

        ## Additional Context
        - Any other important information (deployment, security, performance notes, etc.)

        Keep each section concise but informative. If information is not available in the README, mention "Not specified in README"."""

    def _analyze_readme_content(self, readme_content: str) -> Dict:
        """Analyze README content to extract structured information"""
        prompt = self._create_readme_analysis_prompt(readme_content)
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.together_client.chat.completions.create(
                model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
                messages=messages,
                max_tokens=1024,
                temperature=0.2,
                top_p=0.9,
                top_k=40,
                repetition_penalty=1.1,
            )

            analysis = response.choices[0].message.content

            # Extract specific sections for database storage
            sections = {}
            current_section = None
            current_content = []

            for line in analysis.split("\n"):
                if line.startswith("## "):
                    if current_section:
                        sections[current_section] = "\n".join(current_content).strip()
                    current_section = line.replace("## ", "").strip()
                    current_content = []
                else:
                    current_content.append(line)

            if current_section:
                sections[current_section] = "\n".join(current_content).strip()

            return {
                "full_analysis": analysis,
                "project_description": sections.get("Project Description", ""),
                "setup_instructions": sections.get("Setup & Installation", ""),
                "key_features": sections.get("Key Features", ""),
                "architecture": sections.get("Architecture & Technology Stack", ""),
                "usage_examples": sections.get("Usage Examples", ""),
                "development_info": sections.get("Development Information", ""),
                "additional_context": sections.get("Additional Context", ""),
            }

        except Exception as e:
            logger.error(f"Failed to analyze README content: {e}")
            return {
                "full_analysis": "Analysis failed",
                "project_description": "",
                "setup_instructions": "",
            }

    async def prepare_repository(self, repo_name) -> Tuple[Path, str]:
        repo_path = self.base_dir / repo_name

        if repo_path.exists():
            await asyncio.to_thread(shutil.rmtree, repo_path)

        return repo_path

    def clone_and_process_repository(
        self, repo_url: str, repo_path: str, branch: str = "main"
    ):
        # Clone repository using LangChain's GitLoader
        try:
            loader = GitLoader(
                clone_url=repo_url,
                branch=branch,
                file_filter=lambda file_path: file_path.endswith(
                    (
                        ".py",
                        ".js",
                        ".java",
                        ".cpp",
                        ".h",
                        ".cs",
                        ".ts",
                        ".go",
                        ".toml",
                        ".md",
                        "txt",
                        ".lock",
                        ".cfg",
                        ".yml",
                        ".yaml",
                        ".conf",
                        ".ini",
                    )
                ),
                repo_path=repo_path,
            )

            documents = loader.load()

            return documents
        except Exception:
            return []

    async def process_repository(
        self,
        job_payload: Dict[str, Any],
        job_tracker_instance: Optional[JobTracker] = None,
        job_tracer: Optional[JobTraceMetaData] = None,
    ) -> ProcessingResult:
        """Process a repository and create context"""

        context_id = job_payload["context_id"]

        start_time = datetime.now(timezone.utc)

        try:

            # -----------------------
            # PRECHECKS
            # -----------------------

            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.PRECHECKS)

            # Get repository information

            repo = await self.repo_repository.find_by_repo_id_user_id(
                str(job_payload["repo_id"]), str(job_payload["user_id"])
            )

            if not repo:

                return ProcessingResult(
                    success=False,
                    context_id=context_id,
                    processing_time=0,
                    chunks_created=0,
                    embeddings_created=0,
                    error_message="Repository not found",
                )

            if job_tracer:
                job_tracer.add_metadata(
                    repository_html_url=repo.html_url,
                )

            # -----------------------
            # AUTH
            # -----------------------

            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.AUTH)

            # Get git credentials
            _ = await self._get_authenticated_git_client(
                job_tracer=job_tracer,
                user_id=job_payload["user_id"],
                git_provider=job_payload["git_provider"],
                git_token=job_payload["git_token"],
            )

            # -----------------------
            # WORKDIR
            # -----------------------
            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.WORKDIR)

            # Fetch repository files
            relative_path = await self.prepare_repository(repo.repo_name)

            # -----------------------
            # SOURCE_FETCH
            # -----------------------

            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.SOURCE_FETCH)

            files = self.clone_and_process_repository(
                repo.html_url, str(relative_path), job_payload.get("branch", "main")
            )

            repo_local = Repo(str(relative_path))
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

            # -----------------------
            # CHUNKING
            # -----------------------
            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.CHUNKING)

            # Process files into chunks
            chunks = self._process_files_to_chunks(files)

            # -----------------------
            # ANALYSIS
            # -----------------------
            _ = await self.analyze_repository(
                chunks,
                relative_path,
                repo.language,
                repo.id,
                job_tracker_instance=job_tracker_instance,
            )

            # -----------------------
            # EMBEDDINGS
            # -----------------------

            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.EMBEDDINGS)

            embeddings = await self._create_embeddings(
                chunks,
                model_api_string="togethercomputer/m2-bert-80M-32k-retrieval",
            )

            # -----------------------
            # VECTOR_STORE
            # -----------------------

            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.VECTOR_STORE)

            # Store in vector database
            _ = await self.code_chunks_repository.store_emebeddings(
                repo_id=str(repo.id),
                user_id=repo.user_id,
                data=embeddings,
                commit_number=commit_hash,
            )

            # Update context completion
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()

            # -----------------------
            # CONTEXT_FINALIZE
            # -----------------------
            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.CONTEXT_FINALIZE)

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
                str(repo.id),
                "failed",
                processing_end_time=datetime.now(timezone.utc),
                total_files=0,
                total_chunks=0,
                total_embeddings=0,
            )

            return ProcessingResult(
                success=False,
                context_id=context_id,
                error_object=e,
                error_message=str(e),
            )

    async def _get_authenticated_git_client(
        self,
        user_id: str,
        git_provider: str,
        git_token: str,
        job_tracer: Optional[JobTraceMetaData] = None,
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

        if job_tracer:
            job_tracer.add_metadata(
                user_email=user.email,
            )

        decrypted_encryption_salt = self.encryption_service.decrypt(
            user.encryption_salt
        )

        decrypted_token = self.encryption_service.decrypt_for_user(
            git_config.token_value, decrypted_encryption_salt
        )

        # Create git client
        test = self.git_client_factory.create_client(git_provider, decrypted_token)
        return test

    def _process_files_to_chunks(self, files: List[Dict]) -> List[Dict]:
        """Process files into code chunks"""
        chunks = []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=700, chunk_overlap=200
        )
        chunks = text_splitter.split_documents(files)
        return chunks

    def _chunk_file_content(self, file_data: Dict, context_id: str) -> List[Dict]:
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

    def _create_comprehensive_analysis_prompt(
        self,
        dependency_files: List[Dict[str, str]],
        readme_analysis: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create a comprehensive analysis prompt combining dependency files and README"""
        files_content = "\n\n".join(
            [
                f"=== {file['file_name']} ({file['language']}) ===\n{file['content']}"
                for file in dependency_files
            ]
        )

        readme_section = ""
        if readme_analysis:
            readme_section = f"""

    --- README ANALYSIS ---
    {readme_analysis.get('full_analysis', 'No README analysis available')}
    --- END README ANALYSIS ---"""

        prompt = f"""You are a senior software engineer tasked with analyzing a codebase. You have access to both dependency files and README analysis.
    
    --- DEPENDENCY FILE CONTENTS START ---
    {files_content}
    --- DEPENDENCY FILE CONTENTS END ---{readme_section}
    
    Based on BOTH the dependency files and README information (if available), provide a comprehensive analysis:
    
    ## Technology & Framework Recognition
    - What frameworks, runtimes, or libraries are being used?
    - What does this indicate about the application (API, CLI, web app, etc.)?
    - Cross-reference with technologies mentioned in README
    - Identify the application type and architecture
    
    ## Purpose & Functionality Analysis
    - Primary purpose based on dependencies AND README description
    - Key features and capabilities
    - Target use cases and domain context
    
    ## Code Generation Strategy
    - Recommended starter code and scaffolding approach
    - Architectural patterns to follow based on both sources
    - Integration points and API design suggestions
    
    ## Best Practices & Guidelines
    - Coding practices specific to this tech stack
    - Security considerations
    - Performance optimization recommendations
    - Testing strategies
    
    ## Development Workflow
    - Setup instructions combining dependency and README info
    - Development environment recommendations
    - Deployment considerations
    - Common pitfalls and solutions
    
    ## Project Context Assessment
    - How well do dependencies align with stated README purpose?
    - Any discrepancies or missing dependencies for described features?
    - Recommendations for project structure improvements
    
    Please be specific, actionable, and highlight any insights gained from combining both information sources."""
        return prompt

    def _get_clean_filename(self, chunk: Document) -> str:
        """Extract and clean filename from chunk metadata"""
        return chunk.metadata.get("file_name", "").strip()

    def _find_matching_language(
        self, file_name: str, valid_languages: List[str]
    ) -> str:
        """Find the first language that matches the file's dependency pattern"""
        for lang in valid_languages:
            if self._matches_dependency_pattern(file_name, DEPENDENCY_FILES[lang]):
                return lang
        return ""

    def _extract_dependency_files(
        self, chunks: List[Document], relative_path: Path, languages: List[str]
    ) -> List[Dict[str, str]]:
        """Extract dependency files content from chunks"""
        dependency_files = []
        processed_files = set()
        valid_languages = [lang for lang in languages if lang in DEPENDENCY_FILES]

        for chunk in chunks:
            file_name = self._get_clean_filename(chunk)
            # Skip if file already processed or invalid
            if not file_name or file_name in processed_files:
                continue

            matching_language = self._find_matching_language(file_name, valid_languages)
            if matching_language:
                dependency_file = self._read_dependency_file(
                    chunk, relative_path, matching_language
                )
                if dependency_file:
                    dependency_files.append(dependency_file)
                    processed_files.add(file_name)

        return dependency_files

    def _matches_dependency_pattern(self, file_name: str, patterns: List[str]) -> bool:
        """Check if file name matches any dependency pattern"""
        for pattern in patterns:
            if "*" in pattern:
                extension = pattern.replace("*", "")
                if file_name.endswith(extension):
                    return True
            elif file_name == pattern:
                return True
        return False

    def _read_dependency_file(
        self, chunk: Document, relative_path: Path, language: str
    ) -> Optional[Dict[str, str]]:
        """Read dependency file content and return file info"""
        try:
            file_name = chunk.metadata.get("file_name", "").strip()
            file_path_chunk = relative_path / chunk.metadata.get("file_path", "")
            file_path = Path(file_path_chunk).resolve()

            if not file_path.exists():
                return None

            with file_path.open("r", encoding="utf-8") as f:
                content = f.read()

            return {"file_name": file_name, "content": content, "language": language}

        except Exception as e:
            logger.warning(f"Could not read dependency file {file_name}: {e}")
            return None

    async def analyze_repository(
        self,
        chunks: List[Document],
        relative_path: Path,
        languages: List[str],
        id: str | UUID,
        job_tracker_instance: Optional[JobTracker] = None,
    ) -> Optional[bool | None]:
        """Analyze repository based on dependency files and save to database"""
        try:
            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.ANALYSIS)

            # Extract dependency files
            dependency_files = self._extract_dependency_files(
                chunks, relative_path, languages
            )

            # Extract and analyze README
            readme_content = self._extract_readme_content(chunks, relative_path)
            readme_analysis = None
            if readme_content:
                readme_analysis = self._analyze_readme_content(readme_content)
            if not dependency_files and not readme_content:
                logger.info("No dependency files or README found for analysis")
                return None

            # Create analysis prompt
            prompt = self._create_comprehensive_analysis_prompt(
                dependency_files, readme_analysis
            )
            # Get analysis from LLM
            messages = [{"role": "user", "content": prompt}]
            response = self.together_client.chat.completions.create(
                model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
                messages=messages,
                max_tokens=2048,
                temperature=0.3,
                top_p=0.9,
                top_k=40,
                repetition_penalty=1.1,
            )

            analysis_content = response.choices[0].message.content

            # Update to database
            await self.context_repository.update_repo_system_reference(
                str(id),
                repo_system_reference=analysis_content,
            )

            logger.info(f"Repository analysis saved with ID: {id}")
            return True

        except Exception as e:
            logger.error(f"Failed to analyze repository: {e}")
            return None

    async def _create_embeddings(
        self,
        chunks: List[Document],
        model_api_string="togethercomputer/m2-bert-80M-32k-retrieval",
    ) -> List[Dict]:
        """Create vector embeddings for code chunks"""

        embeddings = []
        if len(chunks) > 0:
            together_client = AsyncTogether(api_key=settings.TOGETHER_API_KEY)

        if chunks:
            try:
                # Batch process all chunks concurrently
                async def create_embedding(chunk):
                    response = await together_client.embeddings.create(
                        input=chunk.page_content,
                        model=model_api_string,
                    )
                    return {
                        "chunk_id": str(uuid.uuid4()),
                        "embedding": response.data[0].embedding,
                        "model_name": model_api_string,
                        "model_version": "1.0",
                        "vector_dimension": len(response.data[0].embedding),
                        "content": chunk.page_content,
                        "metadata": chunk.metadata,
                        "file_name": chunk.metadata.get("file_name", ""),
                        "file_path": chunk.metadata.get("file_path", ""),
                        "file_size": chunk.metadata.get("file_size", 0),
                    }

                # Process all chunks concurrently
                embeddings = await asyncio.gather(
                    *[create_embedding(chunk) for chunk in chunks],
                    return_exceptions=True,
                )

                # Filter out exceptions and log them
                valid_embeddings = []
                for i, result in enumerate(embeddings):
                    if isinstance(result, Exception):
                        logger.error(
                            f"Failed to create embedding for chunk {i}: {result}"
                        )
                    else:
                        valid_embeddings.append(result)
                embeddings = valid_embeddings

            except Exception as e:
                logger.error(f"Failed to create embeddings: {e}")

        return embeddings
