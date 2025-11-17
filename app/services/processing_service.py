import asyncio
import logging
from pathlib import Path
import shutil
import uuid
from uuid import UUID
import os
import re
import toml
import aiofiles

from models_src import StatusTypes
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from devdox_ai_git.repo_fetcher import RepoFetcher
from git import Repo
from together import Together, AsyncTogether
from datetime import datetime, timezone
from langchain_community.document_loaders import GitLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List, Dict, Any, Optional, Tuple
from typing import List, Dict, Any, Optional, Tuple, Union
from app.handlers.utils.git_managers import retrieve_git_fetcher_or_die
from devdox_ai_git.repo_fetcher import RepoFetcher
from devdox_ai_git.schema.repo import NormalizedGitRepo
from models_src.repositories.repo import TortoiseRepoStore as RepoRepository
from models_src.dto.repo import RepoRequestDTO
from urllib.parse import urlparse
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
from app.exceptions.base_exceptions import DevDoxContextException

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

def get_full_repo_path(url: str) -> str:
    parsed = urlparse(url)
    # parsed.path = '/org1/package_name1' or '/package_name1' or '/org2/team/repo'
    path = parsed.path.lstrip('/')  # remove leading '/'
    return path

class RateLimitError(Exception):
    pass


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
)
async def create_embedding_with_retry(
    chunk: Document,
    semaphore: asyncio.Semaphore,
    model_api_string: str,
    together_client: AsyncTogether,
):
    """Create embedding with automatic retry on rate limit."""
    async with semaphore:
        try:
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
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                logger.warning(f"Rate limit hit, will retry: {e}")
                raise RateLimitError(str(e))
            logger.error(f"Failed to create embedding: {e}")
            raise


class DependencyExtractor:
    """Extract dependencies from different file types"""

    async def extract_python_deps(self, repo_path: str) -> List[str]:
        """Extract Python dependencies from requirements.txt, pyproject.toml, setup.py"""
        dependencies = []

        # Check requirements.txt
        req_file = os.path.join(repo_path, "requirements.txt")

        if os.path.exists(req_file):
            async with aiofiles.open(req_file, 'r') as f:

                content = await f.read()
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extract package name (ignore version specs)
                        pkg_name = \
                        line.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[
                            0].strip()
                        dependencies.append(pkg_name)


        # Check pyproject.toml
        pyproject_file = os.path.join(repo_path, "pyproject.toml")
        if os.path.exists(pyproject_file):

            try:
                with open(pyproject_file, 'r') as f:
                    data = toml.load(f)

                # Poetry dependencies
                if 'tool' in data and 'poetry' in data['tool'] and 'dependencies' in data['tool']['poetry']:
                    deps = data['tool']['poetry']['dependencies']
                    dependencies.extend([k for k in deps.keys() if k != 'python'])

                # PEP 621 dependencies
                if 'project' in data and 'dependencies' in data['project']:
                    for dep in data['project']['dependencies']:
                        pkg_name = dep.split('==')[0].split('>=')[0].split('<=')[0].strip()
                        dependencies.append(pkg_name)
            except Exception as e:
                logger.warning(f"Error parsing pyproject.toml: {e}")

        return dependencies


    async def extract_all_dependencies(self, repo_path: str) -> Dict[str, List[str]]:
        """Extract all types of dependencies"""
        return {
            'python': await self.extract_python_deps(repo_path)

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
        self.dependency_extractor = DependencyExtractor()
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

    async def remove_repository(self, relative_path: str | Path) -> bool:
        """
        Remove a repository based on relative path from base directory.

        Args:
            relative_path: The relative path to the repository (str or Path)

        Returns:
            bool: True if removal was successful, False if repository didn't exist

        Raises:
            ValueError: If the path is invalid or attempts to escape the base directory
            OSError: If removal fails due to permissions or other filesystem issues
        """

        try:
            # Convert to Path object and validate
            relative_path = Path(relative_path)

            # Validate path components
            if not relative_path.parts:
                raise ValueError("Empty path provided")

            # Check for problematic path components
            if any(part in ("..", ".", "") for part in relative_path.parts):
                raise ValueError(f"Path contains invalid components: {relative_path}")

            # Resolve path relative to base directory
            repo_path = (self.base_dir / relative_path).resolve()

            # Security check: ensure resolved path is within base_dir
            base_dir_resolved = self.base_dir.resolve()
            if not str(repo_path).startswith(str(base_dir_resolved)):
                raise ValueError(
                    f"Path '{relative_path}' resolves outside base directory"
                )

        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid path '{relative_path}': {e}")

            # Validate that path exists and is a directory before attempting removal
        if repo_path.exists() and not repo_path.is_dir():
            raise ValueError(f"Path '{repo_path}' exists but is not a directory")

        try:
            logger.info(f"Removing repository at '{repo_path}'...")
            await asyncio.to_thread(shutil.rmtree, repo_path)
            logger.info(f"Successfully removed repository at '{repo_path}'")
            return True

        except FileNotFoundError:
            logger.warning(f"Repository at '{repo_path}' does not exist")
            return False

        except PermissionError as e:
            raise OSError(
                f"Permission denied removing repository at '{repo_path}': {e}"
            )

        except OSError as e:
            raise OSError(f"Failed to remove repository at '{repo_path}': {e}")

    async def prepare_repository(self, repo_name) -> Tuple[Path, str]:
        repo_path = self.base_dir / repo_name

        if repo_path.exists():
            await asyncio.to_thread(shutil.rmtree, repo_path)

        return repo_path

    async def resolve_dependencies(self, repo_path: str, main_repo_name: str,git_provider:str) -> List:
        """Resolve and prepare to clone dependency repositories"""
        dependencies = await self.dependency_extractor.extract_all_dependencies(repo_path)

        dependency_repos = []

        for dep_type, deps in dependencies.items():

            for dep in deps:
                # Try to find repository URL for this dependency
                repo_info = await self._find_dependency_repo_info(dep, dep_type, git_provider)

                if repo_info:
                    dep_repo={
                       "url":repo_info["url"],
                        "name":repo_info["name"],
                        "is_dependency":True,
                        "parent_repo":main_repo_name,
                        "dependency_type":dep_type,
                        "commit":repo_info["commit"]
                    }
                    dependency_repos.append(dep_repo)

        return dependency_repos

    async def _find_dependency_repo_info(
            self, package_name: str, dep_type: str, provider: str
    ) -> Optional[Dict[str, str]]:
        """
        Find and clean repository URL and extract package name for a dependency.

        Handles patterns like:
        - devdox-ai-git @ git+https://github.com/montymobile1/devdox-ai-git@e36ee1a
        - git+https://github.com/org/repo.git
        - package==1.2.3
        """

        # --- 1. Check if dependency includes a Git URL ---
        git_url_pattern = r"(?:git\+)?(https://(?:github\.com|gitlab\.com)[^@\s]+(?:@[a-zA-Z0-9._-]+)?)"
        git_match = re.search(git_url_pattern, package_name)
        if git_match:
            full_url = git_match.group(1).strip()

            # Extract commit hash (if exists after '@')
            commit_match = re.search(r"@([a-fA-F0-9]{6,40})$", full_url)
            commit_hash = commit_match.group(1) if commit_match else None

            # Clean URL (remove commit hash and trailing .git)
            clean_url = re.sub(r"@([a-fA-F0-9]{6,40})$", "", full_url)
            clean_url = clean_url.rstrip(".git")

            # Extract repo name
            name_match = re.search(r"/([^/]+?)(?:\.git|$)", clean_url)
            name = name_match.group(1) if name_match else package_name.strip()

            return {"name": name, "url": clean_url, "commit": commit_hash}

        # --- 2. Clean package name if no direct Git URL is present ---
        cleaned_name = (
            package_name.strip()
            .split("@")[0]
            .split(" ")[0]
            .split("==")[0]
            .split(">=")[0]
            .split("<=")[0]
            .split("[")[0]
            .replace("/", "")
        )

        # --- 3. Determine base URL based on provider ---
        if provider == "github":
            base_url = "https://github.com"
        elif provider == "gitlab":
            base_url = "https://gitlab.com"
        else:
            return None

        # --- 4. Construct potential URLs based on dependency type ---
        if  dep_type == "node":
            potential_urls = [
                f"{base_url}/{cleaned_name}/{cleaned_name}",
                f"{base_url}/{cleaned_name}/node-{cleaned_name}",
            ]
        else:
            return None

        # --- 5. Return structured result ---
        return {"name": cleaned_name, "url": potential_urls[0],"commit":None}

    async def clone_repository_ecosystem(self,
                                         main_repo_url: str,
                                         repo_name: str,
                                         repo_path: str,
                                         branch:str = "main",
                                         language: str = "python",
                                         git_provider:str = "github",
                                         auth_token: Optional[str] = None,
                                         include_dependencies: bool = True) -> Dict[str, str]:
        """Clone main repository and all its dependencies"""

        cloned_paths=[]
        main_documents =  self.clone_and_process_repository(main_repo_url, repo_path,branch)
        cloned_paths.append({repo_name: {"files":main_documents, "url":main_repo_url }})
        if not include_dependencies:
            return cloned_paths
        # Step 2: Resolve dependencies
        try:

            dependency_files =  self._extract_dependency_files_new(Path(repo_path), language)

            dependency_repos = await self.resolve_dependencies(repo_path, repo_name,git_provider)

            # Step 3: Clone dependency repositories
            for dep_repo in dependency_repos:
                try:

                    new_path = os.path.join(repo_path, dep_repo["name"].replace(" ",""))

                    dep_path =  self.clone_and_process_repository(dep_repo["url"], new_path, "main")
                    cloned_paths.append({dep_repo["name"]: {"files":dep_path, "url":dep_repo["url"] }})


                except Exception as e:
                    logger.warning(f"Failed to clone dependency {dep_repo["name"]}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Failed to resolve dependencies for {repo_name}: {e}")

        return cloned_paths

    def clone_and_process_repository(
            self,
            repo_url: str,
            repo_path: str,
            branch: str = "main",
            commit_hash: str = None
    ):
        """
        Clone and process a repository by branch or specific commit.

        Args:
            repo_url: URL of the git repository to clone
            repo_path: Local path where the repository should be cloned
            branch: Branch name to checkout (default: "main")
            commit_hash: Specific commit hash to checkout (takes precedence over branch)

        Returns:
            List of documents loaded from the repository
        """
        import subprocess
        import os
        import shutil
        from langchain_community.document_loaders.git import GitLoader

        try:
            # Clean up existing repository path if it exists
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)

            # Clone repository with timeout

            clone_cmd = ["git", "clone", repo_url, repo_path]
            clone_result = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if clone_result.returncode != 0:

                return []

            # Save current directory and navigate to repo
            original_cwd = os.getcwd()

            try:
                os.chdir(repo_path)

                if commit_hash:
                    # Try direct checkout first
                    checkout_result = subprocess.run(
                        ["git", "checkout", commit_hash],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if checkout_result.returncode != 0:
                        # Fetch all branches and try again

                        subprocess.run(["git", "fetch", "--all"], timeout=60)

                        checkout_result = subprocess.run(
                            ["git", "checkout", commit_hash],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )

                        if checkout_result.returncode != 0:

                            return []

                elif branch != "main":


                    # Try creating local branch tracking remote
                    checkout_result = subprocess.run(
                        ["git", "checkout", "-b", branch, f"origin/{branch}"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if checkout_result.returncode != 0:
                        # Fallback to direct checkout
                        checkout_result = subprocess.run(
                            ["git", "checkout", branch],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )

                        if checkout_result.returncode != 0:

                            return []

                # Log current commit for verification
                try:
                    commit_info = subprocess.run(
                        ["git", "log", "-1", "--format=%H %s"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if commit_info.returncode == 0:
                        current_commit = commit_info.stdout.strip().split(' ')[0]

                except:
                    pass  # Non-critical operation

            finally:
                # Always restore working directory
                os.chdir(original_cwd)

            # Load documents using GitLoader
            loader = GitLoader(
                clone_url=repo_url,
                branch=branch if not commit_hash else None,
                file_filter=lambda file_path: file_path.endswith((
                    ".py", ".js", ".java", ".cpp", ".h", ".cs", ".ts", ".go",
                    ".toml", ".md", ".txt", ".lock", ".cfg", ".yml", ".yaml",
                    ".conf", ".ini", ".json", ".xml", ".sql", ".sh", ".bat"
                )),
                repo_path=repo_path,
            )

            documents = loader.load()

            return documents

        except subprocess.TimeoutExpired:

            return []
        except Exception as e:

            # Clean up on failure
            if os.path.exists(repo_path):
                try:
                    shutil.rmtree(repo_path)
                except:
                    pass
            return []

    async def _job_step_update(self, job_tracker_instance, step: JobLevels):
        if job_tracker_instance:
            await job_tracker_instance.update_step(step)
    
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
            await self._job_step_update(job_tracker_instance, JobLevels.PRECHECKS)

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
            
            await self.context_repository.update_status(
                str(repo.id),
                status=StatusTypes.IN_PROGRESS,
                processing_end_time=repo.processing_end_time,
                total_files=repo.total_files,
                total_chunks=repo.total_chunks,
                total_embeddings=0,
            )
            
            if job_tracer:
                job_tracer.add_metadata(
                    repository_html_url=repo.html_url,
                )

            # -----------------------
            # GRAB USER
            # -----------------------

            user = await self.user_info.find_by_user_id(job_payload["user_id"])

            if job_tracer:
                job_tracer.add_metadata(
                    user_email=user.email,
                )

            decrypted_encryption_salt = self.encryption_service.decrypt(
                user.encryption_salt
            )

            # -----------------------
            # AUTH
            # -----------------------
            await self._job_step_update(job_tracker_instance, JobLevels.AUTH)

            # Get git credentials
            _ = await self._get_authenticated_git_client(
                user_id=user.user_id,
                encryption_salt=decrypted_encryption_salt,
                git_provider=job_payload["git_provider"],
                git_token=job_payload["git_token"],
            )

            git_config = await self.git_label_repository.find_by_user_and_hosting(
                user.user_id, job_payload["git_token"], job_payload["git_provider"]
            )

            # -----------------------
            # WORKDIR
            # -----------------------
            await self._job_step_update(job_tracker_instance, JobLevels.WORKDIR)

            # Fetch repository files
            relative_path = await self.prepare_repository(repo.repo_name)

            # -----------------------
            # SOURCE_FETCH
            # -----------------------
            await self._job_step_update(job_tracker_instance, JobLevels.SOURCE_FETCH)
            repo_id = job_payload["repo_id"]
            files = await self.clone_repository_ecosystem(
                main_repo_url=repo.html_url,
                repo_name=repo.repo_name,
                repo_path=str(relative_path),
                branch=job_payload.get("branch", "main"),
                git_provider=job_payload["git_provider"],
                language=repo.language
            )



            if files is None or len(files) == 0:
                return ProcessingResult(
                    success=False,
                    context_id=context_id,
                    processing_time=0,
                    chunks_created=0,
                    embeddings_created=0,
                    error_message="No files found in repository",
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
            await self._job_step_update(job_tracker_instance, JobLevels.CHUNKING)

            for package_info in files:
                for package_name, package_item in package_info.items():
                    files = package_item['files']
                    parent_repo_id = None

                    repo_check = await self.repo_repository.find_by_user_and_url(
                        user_id= user.user_id, html_url=package_item['url'].replace(".git", "")
                    )

                    if not repo_check:
                        try:
                            git_fetcher = RepoFetcher()
                            fetcher, fetcher_data_mapper = retrieve_git_fetcher_or_die(
                                git_fetcher, git_config.git_hosting
                            )

                            decrypted_label_token = self.encryption_service.decrypt_for_user(
                                git_config.token_value,
                                salt_b64=decrypted_encryption_salt
                            )


                            name_space_path = get_full_repo_path(package_item['url'])

                            repo_data, languages = fetcher.fetch_single_repo(
                                decrypted_label_token, name_space_path
                            )
                            repo_user = fetcher.fetch_repo_user(decrypted_label_token)
                            author_email = ''
                            author_name = ''

                            if git_config.git_hosting == "github":
                                author_name = repo_user.login
                                emails = repo_user.get_emails()
                                author_email = next((e.email for e in emails if e.primary and e.verified), None)


                            else:  # GitHub returns AuthenticatedUser object
                                author_name = repo_user.get("username")
                                author_email = repo_user.get("commit_email")

                            transformed_data: NormalizedGitRepo = fetcher_data_mapper.from_git(repo_data)
                            repo_repository = RepoRepository()
                            repo_check = await repo_repository.save(
                                RepoRequestDTO(
                                    user_id=user.user_id,
                                    token_id=git_config.id,
                                    repo_id=transformed_data.id,
                                    repo_name=transformed_data.repo_name,
                                    description=transformed_data.description,
                                    html_url=transformed_data.html_url,
                                    relative_path=transformed_data.relative_path,
                                    default_branch=transformed_data.default_branch,
                                    forks_count=transformed_data.forks_count,
                                    stargazers_count=transformed_data.stargazers_count,
                                    is_private=transformed_data.private,
                                    visibility=transformed_data.visibility,
                                    size=transformed_data.size,
                                    repo_created_at=transformed_data.repo_created_at,
                                    language=languages,
                                    repo_alias_name=transformed_data.repo_name,
                                    repo_user_reference="",
                                    repo_author_email=author_email,
                                    repo_author_name=author_name,
                                    repo_parent_id=repo_id

                                )
                            )
                        except Exception as e:

                            child_repo = None

                    else:


                        if  str(repo_id) != str(repo_check.repo_id):
                            child_repo = await self.repo_repository.update_repo_parent_id(repo_check.id,   str(repo.id))



                    # Process files into chunks
                    chunks = self._process_files_to_chunks(files)


                    # -----------------------
                    # ANALYSIS
                    # -----------------------
                    _ = await self.analyze_repository(
                        chunks,
                        relative_path,
                        repo_check.language,
                        repo_check.id,
                        job_tracker_instance=job_tracker_instance,
                    )

                    # -----------------------
                    # EMBEDDINGS
                    # -----------------------
                    await self._job_step_update(job_tracker_instance, JobLevels.EMBEDDINGS)

                    embeddings = await self._create_embeddings(
                        chunks,
                        model_api_string="togethercomputer/m2-bert-80M-32k-retrieval",
                    )
                    # -----------------------
                    # VECTOR_STORE
                    # -----------------------
                    await self._job_step_update(job_tracker_instance, JobLevels.VECTOR_STORE)

                    # Encrypt all contents
                    for embed in embeddings:
                        content = embed.get("content")
                        encrypted_content = self.encryption_service.encrypt_for_user(
                            content, decrypted_encryption_salt
                        )
                        embed["encrypted_content"] = encrypted_content

                    # Store in vector database
                    _ = await self.code_chunks_repository.store_emebeddings(
                        repo_id=str(repo_check.id),
                        user_id=repo_check.user_id,
                        data=embeddings,
                        commit_number=commit_hash,
                    )

            # Update context completion
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()

            # -----------------------
            # CONTEXT_FINALIZE
            # -----------------------
            await self._job_step_update(job_tracker_instance, JobLevels.CONTEXT_FINALIZE)

            await self.context_repository.update_status(
                str(repo.id),
                status=StatusTypes.COMPLETED,
                processing_end_time=end_time,
                total_files=len(files),
                total_chunks=len(chunks),
                total_embeddings=len(embeddings),
            )
            await self.remove_repository(relative_path)

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
                status=StatusTypes.FAILED,
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
        self, user_id: str, encryption_salt: str, git_provider: str, git_token: str
    ):
        """Get authenticated git client for user"""

        # Get user's git configuration
        git_config = await self.git_label_repository.find_by_user_and_hosting(
            user_id, git_token, git_provider
        )

        if not git_config:
           raise DevDoxContextException(user_message=f"No {git_provider} configuration found for user")

        # Decrypt the stored token
        decrypted_token = self.encryption_service.decrypt_for_user(
            git_config.token_value, encryption_salt
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

    def _extract_dependency_files_new(
            self, relative_path: Path, languages: List[str]
    ) -> List[Dict[str, str]]:
        """Extract dependency files content directly from the filesystem."""
        dependency_files = []
        processed_files = set()
        valid_languages = [lang for lang in languages if lang in DEPENDENCY_FILES]

        # Traverse the directory tree under relative_path
        for lang in valid_languages:
            patterns = DEPENDENCY_FILES.get(lang, [])

            for pattern in patterns:
                for file_path in relative_path.rglob(pattern):
                    if not file_path.is_file():
                        continue

                    file_name = file_path.name
                    if file_name in processed_files:
                        continue

                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                    except Exception as e:
                        continue

                    dependency_files.append(
                        {
                            "language": lang,
                            "file_name": file_name,
                            "relative_path": str(file_path.relative_to(relative_path)),
                            "content": content,
                        }
                    )
                    processed_files.add(file_name)

        return dependency_files

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
            await self._job_step_update(job_tracker_instance, JobLevels.ANALYSIS)

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
        max_concurrent: int = 40,
    ) -> List[Dict]:
        """Process chunks with concurrency control and retry logic."""
        semaphore = asyncio.Semaphore(max_concurrent)

        together_client = AsyncTogether(api_key=settings.TOGETHER_API_KEY)

        embeddings = await asyncio.gather(
            *[
                create_embedding_with_retry(
                    chunk, semaphore, model_api_string, together_client
                )
                for chunk in chunks
            ],
            return_exceptions=True,
        )

        # Separate successful and failed embeddings
        successful_embeddings = []
        failed_count = 0

        for i, emb in enumerate(embeddings):
            if isinstance(emb, Exception):
                logger.error(f"Chunk {i} permanently failed: {emb}")
                failed_count += 1
            elif emb is not None:
                successful_embeddings.append(emb)

        logger.info(
            f"Successfully processed {len(successful_embeddings)}/{len(chunks)} chunks"
        )
        if failed_count > 0:
            logger.warning(f"{failed_count} chunks failed after all retries")

        return successful_embeddings
