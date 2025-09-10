"""
Locust Test Generator

Generates Locust performance test files from parsed OpenAPI endpoints.
"""

import json
import re
import random
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import textwrap
import black

import logging
from dataclasses import dataclass
from datetime import datetime
import textwrap
from datetime import datetime
from typing import Dict, Any

from app.handlers.utils.open_ai_parser import (
    Endpoint,
    Parameter,
    RequestBody,
    Response,
    ParameterType,
)

logger = logging.getLogger(__name__)


@dataclass
class TestDataConfig:
    """Configuration for test data generation"""

    string_length: int = 10
    integer_min: int = 1
    integer_max: int = 1000
    array_size: int = 3
    use_realistic_data: bool = True


class LocustTestGenerator:
    """Generates Locust performance test files from OpenAPI endpoints"""

    def __init__(self, test_config: TestDataConfig = None):
        self.test_config = test_config or TestDataConfig()
        self.generated_files = {}
        self.auth_token = None
        self.user_data = {}
        self.request_count = 0

    def fix_indent(self, base_files: Dict[str, str]) -> Dict[str, str]:
        """Fix indentation for generated files"""
        """
            Fixes indentation and formatting of Python code using Black.
            """
        try:
            mode = black.Mode()
            updated_data = {}

            for key, value in base_files.items():
                if isinstance(value, str):
                    try:
                        formatted_code = black.format_str(value, mode=mode)
                        updated_data[key] = formatted_code
                    except Exception:
                        # If it's not valid Python code, keep the original
                        updated_data[key] = value
                else:
                    updated_data[key] = value

            return updated_data

        except Exception as e:
            print(f"exception occurred: {e}")
            return base_files

    def generate_from_endpoints(
        self,
        endpoints: List[Endpoint],
        api_info: Dict[str, Any],
        output_dir: str = "locust_tests",
    ) ->Tuple[Dict[str, str], List[Dict[str, Any]]]:
        """
        Generate complete Locust test suite from parsed endpoints

        Args:
            endpoints: List of parsed Endpoint objects
            api_info: API information dictionary
            output_dir: Output directory for generated files

        Returns:
            Dictionary of filename -> file content
        """
        grouped_enpoint= self._group_endpoints_by_tag(endpoints)
        workflows_files= self.generate_workflows(grouped_enpoint, api_info)

        self.generated_files = {

            "locustfile.py": self._generate_main_locustfile(endpoints, api_info, list(grouped_enpoint.keys())),
            "test_data.py": self._generate_test_data_file(endpoints),
            "config.py": self._generate_config_file(api_info),
            "utils.py": self._generate_utils_file(),
            "custom_flows.py": self._generate_custom_flows_file(endpoints),
            "requirements.txt": self._generate_requirements_file(),
            'README.md': self._generate_readme_file(api_info),
            ".env.example": self._generate_env_example()
        }
        return self.generated_files, workflows_files, grouped_enpoint



    def generate_workflows(
            self, endpoints: Dict[str, List[Any]], api_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate the workflows Locust test files with proper structure and no duplicates
        """
        try:
            workflows: List = []

            for group, group_endpoints in endpoints.items():
                task_methods: List[str] = []

                for endpoint in group_endpoints:
                    try:
                        task_method = self._generate_task_method(endpoint)
                        if task_method:
                            task_methods.append(task_method)
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Failed to generate task method for {getattr(endpoint, 'path', '?')}: {e}"
                        )
                        continue

                if not task_methods:
                    logger.warning(f"No task methods generated from group {group}")
                    task_methods.append(self._generate_default_task_method())

                indented_task_methods = self._indent_methods(task_methods, indent_level=1)
                file_content = self._build_endpoint_template(api_info, indented_task_methods, group)
                file_name = f"{group}_workflow.py".replace("-", "_")

                workflows.append({ file_name: file_content})

            workflows.append({f"base_workflow.py":  self.generate_base_common_file(api_info)})

            return workflows

        except Exception as e:
            logger.error(f"❌ Failed to generate test suite: {e}")
            return []



    def generate_base_common_file(self, api_info: Dict[str, Any]) -> str:
        template = f"""\
        \"\"\"
        Locust performance tests for {api_info.get('title', 'API')}
        Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        API Information:
        - Title: {api_info.get('title', 'Unknown')}
        - Version: {api_info.get('version', 'Unknown')}
        - Base URL: {api_info.get('base_url', 'http://localhost')}
        \"\"\"

        from locust import HttpUser, task, between, events, SequentialTaskSet
        import json
        import logging
        from typing import Dict, Any, Optional
        from urllib.parse import urljoin

        from test_data import TestDataGenerator
        from utils import ResponseValidator, RequestLogger, PerformanceMonitor
        from config import LoadTestConfig

        # Configure logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        # Initialize components
        config = LoadTestConfig()
        data_generator = TestDataGenerator()
        response_validator = ResponseValidator()
        performance_monitor = PerformanceMonitor()


        class BaseTaskMethods:
            \"\"\"Mixin class with common task functionality - no inheritance conflicts\"\"\"
            
            def __init__(self, *args, **kwargs):
        
                super().__init__(*args, **kwargs)
                self._initialize_attributes()
    
            def _initialize_attributes(self):
                \"\"\"Initialize all required attributes\"\"\"
                if not hasattr(self, 'auth_token'):
                    self.auth_token = None
                if not hasattr(self, 'user_data'):
                    self.user_data = {{}}
                if not hasattr(self, 'request_count'):
                    self.request_count = 0
                if not hasattr(self, 'default_headers'):
                    self._setup_authentication()
                    self._setup_headers()
                    
                def on_start(self):
                    \"\"\"Initialize user session\"\"\"
                    # Ensure attributes are initialized
                    self._initialize_attributes()
                
                    logger.info(f"TaskSet {self.__class__.__name__} started")

            def on_stop(self):
                \"\"\"Cleanup when user stops\"\"\"
                if hasattr(self, 'request_count'):
                    logger.info(f"TaskSet {self.__class__.__name__} stopped after {self.request_count} requests")
                else:
                    logger.info(f"TaskSet {{self.__class__.__name__}} stopped after {{self.request_count}} requests")

            def _setup_authentication(self):
                \"\"\"Setup authentication (override in subclasses if needed)\"\"\"
                 if not hasattr(self, 'auth_token'):
                    self.auth_token = None
                    
                if config.api_key:
                    self.auth_token = config.api_key

            def _setup_headers(self):
                \"\"\"Setup default headers for all requests\"\"\"
                 if not hasattr(self, 'auth_token'):
                    self._setup_authentication()
                self.default_headers = {{
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Locust-LoadTest/1.0"
                }}
                if self.auth_token:
                    self.default_headers["Authorization"] = f"Bearer {{self.auth_token}}"

            def make_request(self, method: str, path: str, **kwargs) -> Optional[Dict]:
                \"\"\"Make HTTP request with logging, validation, and monitoring\"\"\"
                self._initialize_attributes()
        
                self.request_count += 1

                try:
                    # Merge headers
                    request_headers = {{**self.default_headers, **kwargs.get("headers", {{}})}}

                    # Set content-type for POST/PUT/PATCH
                    if method.upper() in ["POST", "PUT", "PATCH"]:
                        if "json" in kwargs:
                            request_headers["Content-Type"] = "application/json"
                        elif "data" in kwargs and isinstance(kwargs["data"], dict):
                            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

                    kwargs["headers"] = request_headers

                    # Log request
                    RequestLogger.log_request(method, path, kwargs)

                    with self.client.request(
                        method=method,
                        url=urljoin(config.base_url, path),
                        catch_response=True,
                        **kwargs
                    ) as response:
                        # Validate and monitor
                        is_valid = response_validator.validate_response(response, method, path)
                        performance_monitor.record_response(response, method, path)

                        if not is_valid:
                            response.failure(f"Response validation failed for {{method}} {{path}}")
                            return None

                        try:
                            return response.json() if response.content else None
                        except json.JSONDecodeError:
                            if response.status_code < 400:
                                return {{"raw_content": response.text}}
                            response.failure(f"Invalid JSON response for {{method}} {{path}}")
                            return None

                except Exception as e:
                    logger.error(f"Request failed {{method}} {{path}}: {{e}}")
                    return None

            def _store_response_data(self, method_name: str, data: Dict):
                \"\"\"Store response data for future requests\"\"\"
                if not hasattr(self, 'user_data'):
                self.user_data = {{}}
                if data:
                    self.user_data[method_name] = data

            def _get_stored_data(self, method_name: str, key: str = None):
                \"\"\"Retrieve stored response data from previous requests\"\"\"
                stored_data = self.user_data.get(method_name)
                if stored_data and key:
                    return stored_data.get(key)
                return stored_data


        class BaseAPIUser(HttpUser):
            \"\"\"Base class for API users with common functionality\"\"\"

            abstract = True
            wait_time = between(0.5, 1.5)

            def on_start(self):
                \"\"\"Initialize user session\"\"\"
                self.auth_token = None
                self.user_data = {{}}
                self.request_count = 0

                # Setup authentication if needed
                self._setup_authentication()

                # Initialize session headers
                self._setup_headers()

                logger.info(f"User {{self.__class__.__name__}} started")

            def on_stop(self):
                \"\"\"Cleanup when user stops\"\"\"
                logger.info(f"User {{self.__class__.__name__}} stopped after {{self.request_count}} requests")

            def _setup_authentication(self):
                \"\"\"Setup authentication (override in subclasses if needed)\"\"\"
                if config.api_key:
                    self.auth_token = config.api_key

            def _setup_headers(self):
                \"\"\"Setup default headers for all requests\"\"\"
                self.default_headers = {{
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Locust-LoadTest/1.0"
                }}
                if self.auth_token:
                    self.default_headers["Authorization"] = f"Bearer {{self.auth_token}}"
        """
        return textwrap.dedent(template)

    def _build_endpoint_template(
            self, api_info: Dict[str, Any], task_methods_content: str,group:str
    ) -> str:
        template = f"""\
       \"\"\"
       Locust performance tests for {group}
       Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

       API Information:
       - Title: {api_info.get('title', 'Unknown')}
       - Version: {api_info.get('version', 'Unknown')}
       - Base URL: {api_info.get('base_url', 'http://localhost')}
       \"\"\"

       from locust import HttpUser, task, between, events
       from locust.runners import MasterRunner
       import json
       import random
       import logging
       from typing import Dict, Any, Optional
       from urllib.parse import urljoin

       from test_data import TestDataGenerator
       from locust import SequentialTaskSet, task
       from utils import ResponseValidator, RequestLogger, PerformanceMonitor
       from workflows.base_workflow import BaseAPIUser, BaseTaskMethods
       from config import LoadTestConfig

       # Configure logging
       logging.basicConfig(level=logging.INFO)
       logger = logging.getLogger(__name__)

       # Initialize components
       config = LoadTestConfig()
       data_generator = TestDataGenerator()
       response_validator = ResponseValidator()
       performance_monitor = PerformanceMonitor()


       class {group}TaskMethods(SequentialTaskSet, BaseTaskMethods):
           \"\"\"Mixin class containing all API task methods\"\"\"

       {task_methods_content}




       """
        return textwrap.dedent(template)

    def _generate_main_locustfile(
        self, endpoints: List[Any], api_info: Dict[str, Any], groups: List[str]
    ) -> str:
        """
        Generate the main Locust test file with proper structure and no duplicates

        Args:
            endpoints: List of parsed Endpoint objects
            api_info: API information dictionary

        Returns:
            Complete locustfile.py content as string
        """
        try:
            # Generate task methods for each endpoint
            task_methods = []
            for endpoint in endpoints:
                try:
                    task_method = self._generate_task_method(endpoint)
                    if task_method:
                        task_methods.append(task_method)
                except Exception as e:
                    logger.warning(
                        f"Failed to generate task method for 230 {endpoint.path}: {e}"
                    )
                    continue

            if not task_methods:
                logger.warning("No task methods generated from endpoints")
                # Generate a default task method
                task_methods.append(self._generate_default_task_method())

            # Properly indent task methods for class inclusion
            indented_task_methods = self._indent_methods(task_methods, indent_level=1)
            indented_task_methods = ""
            # Generate the complete file content
            return self._build_locustfile_template(
                api_info=api_info, task_methods_content=indented_task_methods, groups=groups
            )

        except Exception as e:
            logger.error(f"Failed to generate test suite: {e}")
            # Return fallback files
            return self._generate_fallback_locustfile(api_info)

    def _indent_methods(self, task_methods: List[str], indent_level: int = 1) -> str:
        """Properly indent task methods for class inclusion"""
        indented_methods = []
        for method in task_methods:
            lines = method.split("\n")
            indented_lines = []
            first_nonempty = True

            for line in lines:
                if line.strip():
                    stripped_line = line.lstrip()
                    if first_nonempty:
                        # First non-empty line → indent once (for @task or def)
                        indented_lines.append("    " * indent_level + stripped_line)
                        first_nonempty = False
                    else:
                        # Method body → indent deeper
                        indented_lines.append(
                            "    " * (indent_level + 1) + stripped_line
                        )
                else:
                    indented_lines.append("")
            indented_methods.append("\n".join(indented_lines))

        return "\n\n".join(indented_methods)

    def _generate_fallback_locustfile(self, api_info: Dict[str, Any]) -> str:
        """Generate a basic fallback locustfile when main generation fails"""
        return f'''"""
    Fallback Locust test file for {api_info.get('title', 'API')}
    Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """

    from locust import HttpUser, task, between
    import logging

    logger = logging.getLogger(__name__)


    class BasicAPIUser(HttpUser):
        wait_time = between(1, 5)

        @task(1)
        def health_check(self):
            """Basic health check"""
            with self.client.get("/health", catch_response=True) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Health check failed: {{response.status_code}}")


    if __name__ == "__main__":
        print("Running fallback Locust test")
    '''

    import textwrap
    from datetime import datetime
    from typing import Dict, Any

    def _build_locustfile_template(
            self, api_info: Dict[str, Any], task_methods_content: str,
            groups: List[str]
    ) -> str:
        import_group_tasks = ""
        tasks = []
        for group in groups:
            file_name = group.lower().replace("-", "_")
            class_name = group.replace("-", "")
            import_group_tasks += f"""from workflows.{file_name}_workflow import {class_name}TaskMethods\n"""
            tasks.append(f"{class_name}TaskMethods")
        tasks_str = '[' + ','.join(tasks) + ']'
        template = f"""\
    \"\"\"
    Locust performance tests for {api_info.get('title', 'API')}
    Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    API Information:
    - Title: {api_info.get('title', 'Unknown')}
    - Version: {api_info.get('version', 'Unknown')}
    - Base URL: {api_info.get('base_url', 'http://localhost')}
    \"\"\"

    from locust import HttpUser, task, between, events
    from locust.runners import MasterRunner
    import json
    import random
    import logging
    from typing import Dict, Any, Optional
    from urllib.parse import urljoin
    from workflows.base_workflow import BaseAPIUser
    {import_group_tasks}

    from test_data import TestDataGenerator
    from utils import ResponseValidator, RequestLogger, PerformanceMonitor
    from config import LoadTestConfig

    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Initialize components
    config = LoadTestConfig()
    data_generator = TestDataGenerator()
    response_validator = ResponseValidator()
    performance_monitor = PerformanceMonitor()


   
    class APITaskMethods:
        \"\"\"Mixin class containing all API task methods\"\"\"

        #{task_methods_content}
  
        tasks = {str(tasks_str)}


    {self._generate_user_classes(tasks_str)}


    # Event handlers
    @events.request.add_listener
    def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
        performance_monitor.on_request_event(
            request_type, name, response_time, response_length, exception, context
        )


    @events.test_start.add_listener
    def on_test_start(environment, **kwargs):
        logger.info("Load test starting...")
        performance_monitor.test_start()


    @events.test_stop.add_listener
    def on_test_stop(environment, **kwargs):
        logger.info("Load test stopping...")
        performance_monitor.test_stop()
        performance_monitor.generate_report()


    if __name__ == "__main__":
        from locust.main import main
        main()
    """
        return textwrap.dedent(template)

    def _generate_default_task_method(self) -> str:
        """Generate a default task method when no endpoints are available"""
        return '''@task(1)
    def default_health_check(self):
        """Default health check task"""
        try:
            response_data = self.make_request(
                method="get",
                path="/health"
            )

            if response_data:
                self._store_response_data("health_check", response_data)

        except Exception as e:
            logger.error(f"Health check task failed: {e}")
    '''

    def _generate_task_method(self, endpoint: Any) -> str:
        """Generate a Locust task method for a single endpoint with improved structure"""
        try:
            method_name = self._generate_method_name(endpoint)
            path_with_params = self._generate_path_with_params(endpoint)
            weight = self._get_task_weight(getattr(endpoint, "method", "GET"))

            # Build the task method with proper error handling
            task_method = f'''@task({weight})
    def {method_name}(self):
        """
        {getattr(endpoint, 'summary', f'{getattr(endpoint, "method", "GET")} {getattr(endpoint, "path", "")}')}
        {getattr(endpoint, 'description', '')}
        """
        try:
            # Generate path parameters
            {self._generate_path_params_code(endpoint)}

            # Generate query parameters
            {self._generate_query_params_code(endpoint)}

            # Generate request body
            {self._generate_request_body_code(endpoint)}

            # Make the request
            response_data = self.make_request(
                method="{getattr(endpoint, 'method', 'GET').lower()}",
                path=f"{path_with_params}",
                {self._generate_request_kwargs(endpoint)}
            )

            if response_data:
                # Store response data for dependent requests
                self._store_response_data("{method_name}", response_data)

        except Exception as e:
            logger.error(f"Task {method_name} failed: {{e}}")
    '''
            return task_method

        except Exception as e:
            logger.error(f"Failed to generate task method for 535 endpoint: {e}")
            return None

    def _generate_method_name(self, endpoint: Endpoint) -> str:
        """Generate a valid Python method name from endpoint"""
        if endpoint.operation_id:
            # Use operation ID if available
            name = endpoint.operation_id
        else:
            # Generate name from method and path
            path_parts = [
                part
                for part in endpoint.path.split("/")
                if part and not part.startswith("{")
            ]
            name = f"{endpoint.method.lower()}_{'_'.join(path_parts)}"

        # Clean up the name
        name = re.sub(r"[^\w]", "_", name)
        name = re.sub(r"_+", "_", name)
        name = name.strip("_")

        return name if name else f"{endpoint.method.lower()}_endpoint"

    def _generate_path_with_params(self, endpoint: Endpoint) -> str:
        """Generate path with parameter placeholders"""
        path = endpoint.path

        # Replace path parameters with f-string format
        for param in endpoint.parameters:
            if param.location.value == "path":
                path = path.replace(f"{{{param.name}}}", f"{{{param.name}}}")

        return path

    def _generate_path_params_code(self, endpoint: Endpoint) -> str:
        """Generate code for path parameters"""
        path_params = [p for p in endpoint.parameters if p.location.value == "path"]

        if not path_params:
            return "# No path parameters"

        code_lines = []
        for param in path_params:
            if param.type.startswith("integer"):
                code_lines.append(f"{param.name} = data_generator.generate_integer()")
            elif param.type == "string":
                if "id" in param.name.lower():
                    code_lines.append(f"{param.name} = data_generator.generate_id()")
                else:
                    code_lines.append(
                        f"{param.name} = data_generator.generate_string()"
                    )
            else:
                code_lines.append(
                    f'{param.name} = data_generator.generate_value("{param.type}")'
                )

        return "\n".join(code_lines)

    def _generate_query_params_code(self, endpoint: Endpoint) -> str:
        """Generate code for query parameters"""
        query_params = [p for p in endpoint.parameters if p.location.value == "query"]

        if not query_params:
            return "params = {}"

        code_lines = ["params = {"]
        for param in query_params:
            if (
                not param.required and random.random() > 0.7
            ):  # Sometimes skip optional params
                continue

            if param.type.startswith("integer"):
                default = param.default if param.default is not None else "None"
                code_lines.append(
                    f'"{param.name}": data_generator.generate_integer(default={default}),'
                )
            elif param.type == "string":
                default = f'"{param.default}"' if param.default else "None"
                code_lines.append(
                    f'"{param.name}": data_generator.generate_string(default={default}),'
                )
            elif param.type == "boolean":
                code_lines.append(f'"{param.name}": data_generator.generate_boolean(),')
            else:
                code_lines.append(
                    f'"{param.name}": data_generator.generate_value("{param.type}"),'
                )

        code_lines.append("            }")

        return "\n".join(code_lines)

    def _generate_request_body_code(self, endpoint: Endpoint) -> str:
        """Generate code for request body"""
        if not endpoint.request_body:
            return "json_data = None"

        if endpoint.request_body.content_type == "application/json":
            return f"""json_data = data_generator.generate_json_data(
                schema={json.dumps(endpoint.request_body.schema, indent=16)}
            )"""
        elif endpoint.request_body.content_type == "application/x-www-form-urlencoded":
            return "data = data_generator.generate_form_data()"
        else:
            return "json_data = {}"

    def _generate_request_kwargs(self, endpoint: Endpoint) -> str:
        """Generate kwargs for the request method"""
        kwargs = []

        # Add query parameters
        query_params = [p for p in endpoint.parameters if p.location.value == "query"]
        if query_params:
            kwargs.append("params=params")

        # Add request body
        if endpoint.request_body:
            if endpoint.request_body.content_type == "application/json":
                kwargs.append("json=json_data")
            elif (
                endpoint.request_body.content_type
                == "application/x-www-form-urlencoded"
            ):
                kwargs.append("data=data")

        # Add headers if needed
        header_params = [p for p in endpoint.parameters if p.location.value == "header"]
        if header_params:
            kwargs.append("headers=headers")

        return ",\n                ".join(kwargs)

    def _get_task_weight(self, method: str) -> int:
        """Get task weight based on HTTP method"""
        weights = {
            "GET": 5,  # Most frequent
            "POST": 2,  # Common
            "PUT": 1,  # Less frequent
            "PATCH": 1,  # Less frequent
            "DELETE": 1,  # Least frequent
            "HEAD": 3,  # Moderate
            "OPTIONS": 1,  # Rare
        }
        return weights.get(method.upper(), 1)

    def _group_endpoints_by_tag(
        self, endpoints: List[Endpoint]
    ) -> Dict[str, List[Endpoint]]:
        """Group endpoints by their tags"""
        grouped = {}

        for endpoint in endpoints:
            print(f"endpoint: {endpoint}")
            tags = endpoint.tags if endpoint.tags else ["default"]
            print(f"tags: {tags}")
            for tag in tags:
                print(f"tag: {tag}")
                if tag not in grouped:
                    grouped[tag] = []
                grouped[tag].append(endpoint)
        print("grouped", grouped)

        return grouped

    def _generate_all_task_methods_string(self, endpoints: List[Endpoint]) -> str:
        """Generate all task methods as a properly indented string"""
        methods = []
        for endpoint in endpoints:
            method_code = self._generate_task_method(endpoint)
            methods.append(method_code)

        return "\n".join(methods)

    def _generate_user_classes(self, tasks:str) -> str:
        """
        **FIXED: Generate user classes with proper structure**
        """

        return f'''
    class LightUser(BaseAPIUser, BaseTaskMethods):
        """Light user with occasional API usage patterns"""
        weight = 3
        wait_time = between(3, 8)  # Longer wait times

        def on_start(self):
            super().on_start()
            self.user_type = "light"
   

    class RegularUser( BaseAPIUser, BaseTaskMethods):
        """Regular user with normal API usage patterns"""
        weight = 4
        wait_time = between(1, 4)  # Moderate wait times
        
        def on_start(self):
            super().on_start()
            self.user_type = "regular"
        


    class PowerUser( BaseAPIUser, BaseTaskMethods):
        """Power user with heavy API usage patterns"""
        weight = 3
        wait_time = between(0.5, 2)  # Shorter wait times

        def on_start(self):
            super().on_start()
            self.user_type = "power"
            

    '''

    def _generate_test_data_file(self, endpoints: List[Endpoint]) -> str:
        """Generate test_data.py file content"""

        # Base skeleton
        content = textwrap.dedent(
            """\
            \"\"\"
            Test Data Generator for Locust Performance Tests

            Provides realistic test data generation for API endpoints.
            \"\"\"

            import random
            import string
            import uuid
            from datetime import datetime, timedelta
            from typing import Any, Dict, List, Optional, Union
            from faker import Faker
            import json

            fake = Faker()

            class TestDataGenerator:
                \"\"\"Generates realistic test data for API testing\"\"\"

                def __init__(self, seed: Optional[int] = None):
                    if seed:
                        random.seed(seed)
                        Faker.seed(seed)

                    self.generated_ids = set()
                    self.user_sessions = {}

                def generate_json_data(self, schema: Dict[str, Any], required_only: bool = False) -> Dict[str, Any]:
                    \"\"\"
                    Generate realistic JSON data based on JSON Schema

                    Args:
                        schema: JSON Schema dictionary
                        required_only: If True, only generate required fields

                    Returns:
                        Dictionary with generated test data
                    \"\"\"
                    if not isinstance(schema, dict):
                        return {}

                    schema_type = schema.get('type', 'object')

                    if schema_type == 'object':
                        return self._generate_object_data(schema, required_only)
                    elif schema_type == 'array':
                        return self._generate_array_data(schema)
                    elif schema_type == 'string':
                        return self._generate_string_value(schema)
                    elif schema_type == 'integer':
                        return self._generate_integer_value(schema)
                    elif schema_type == 'number':
                        return self._generate_number_value(schema)
                    elif schema_type == 'boolean':
                        return self._generate_boolean_value(schema)
                    else:
                        return None

                def _generate_object_data(self, schema: Dict[str, Any], required_only: bool = False) -> Dict[str, Any]:
                    \"\"\"Generate object data from schema properties\"\"\"
                    result = {}
                    properties = schema.get('properties', {})
                    required = schema.get('required', [])

                    for prop_name, prop_schema in properties.items():
                        if required_only and prop_name not in required:
                            continue

                        if '$ref' in prop_schema:
                            result[prop_name] = self._handle_reference(prop_schema['$ref'])

                    return result

                def _generate_array_data(self, schema: Dict[str, Any]) -> List[Any]:
                    \"\"\"Generate array data from schema\"\"\"
                    items_schema = schema.get('items', {})
                    min_items = schema.get('minItems', 1)
                    max_items = schema.get('maxItems', 3)

                    array_length = random.randint(min_items, max_items)
                    result = []

                    for _ in range(array_length):
                        if '$ref' in items_schema:
                            result.append(self._handle_reference(items_schema['$ref']))
                        else:
                            result.append(self.generate_json_data(items_schema))

                    return result

                def _generate_integer_value(self, schema: Dict[str, Any]) -> int:
                    \"\"\"Generate integer value based on schema constraints\"\"\"
                    minimum = schema.get('minimum', 0)
                    maximum = schema.get('maximum', 1000)
                    multiple_of = schema.get('multipleOf')

                    value = random.randint(minimum, maximum)

                    if multiple_of:
                        value = (value // multiple_of) * multiple_of

                    return value

                def _generate_number_value(self, schema: Dict[str, Any]) -> float:
                    \"\"\"Generate number/float value based on schema constraints\"\"\"
                    minimum = schema.get('minimum', 0.0)
                    maximum = schema.get('maximum', 1000.0)
                    multiple_of = schema.get('multipleOf')

                    value = random.uniform(minimum, maximum)

                    if multiple_of:
                        value = round((value / multiple_of)) * multiple_of
                    else:
                        value = round(value, 2)

                    return value

                def _generate_boolean_value(self, schema: Dict[str, Any]) -> bool:
                    \"\"\"Generate boolean value\"\"\"
                    return random.choice([True, False])

                def _handle_reference(self, ref: str) -> Any:
                    \"\"\"Handle $ref references in schema\"\"\"
                    ref_name = ref.split('/')[-1]
                    ref_lower = ref_name.lower()

                    if 'hosting' in ref_lower or 'provider' in ref_lower:
                        return random.choice(['github', 'gitlab', 'bitbucket'])
                    elif 'role' in ref_lower:
                        return random.choice(['admin', 'user', 'viewer'])
                    elif 'status' in ref_lower:
                        return random.choice(['active', 'inactive', 'pending'])
                    elif 'type' in ref_lower:
                        return random.choice(['primary', 'secondary', 'tertiary'])
                    else:
                        return f"{ref_name.lower()}_value_{random.randint(1, 100)}"

                def _generate_by_name_pattern(self, prop_name: str) -> str:
                    \"\"\"Generate value based on property name patterns as fallback\"\"\"
                    prop_name_lower = prop_name.lower()

                    if 'email' in prop_name_lower:
                        return fake.email()
                    elif any(keyword in prop_name_lower for keyword in ['name', 'label']):
                        return fake.catch_phrase()
                    elif any(keyword in prop_name_lower for keyword in ['token', 'key']):
                        return ''.join(random.choices(string.ascii_letters + string.digits, k=32))
                    elif 'id' in prop_name_lower:
                        return str(uuid.uuid4())
                    elif 'url' in prop_name_lower:
                        return fake.url()
                    else:
                        return self.random_string(10)

                def _generate_string_value(self, schema: Dict[str, Any], prop_name: str = "") -> str:
                    \"\"\"Generate string value based on schema constraints and property name\"\"\"
                    min_length = schema.get('minLength', 1)
                    max_length = schema.get('maxLength', 50)
                    enum_values = schema.get('enum')
                    prop_name_lower = prop_name.lower()

                    if enum_values:
                        return random.choice(enum_values)

                    if any(keyword in prop_name_lower for keyword in ['email', 'mail']):
                        return fake.email()

                    if any(keyword in prop_name_lower for keyword in ['name', 'label', 'title']):
                        if 'first' in prop_name_lower:
                            return fake.first_name()
                        elif 'last' in prop_name_lower:
                            return fake.last_name()
                        elif 'company' in prop_name_lower:
                            return fake.company()
                        else:
                            return fake.catch_phrase()[:max_length]

                    if any(keyword in prop_name_lower for keyword in ['token', 'key', 'secret', 'password']):
                        token_length = min(max_length, 32)
                        return ''.join(random.choices(string.ascii_letters + string.digits, k=token_length))

                    if any(keyword in prop_name_lower for keyword in ['url', 'uri', 'endpoint']):
                        return fake.url()

                    if 'phone' in prop_name_lower:
                        return fake.phone_number()

                    if 'address' in prop_name_lower:
                        return fake.address().replace('\\n', ', ')

                    if any(keyword in prop_name_lower for keyword in ['description', 'comment', 'note', 'text']):
                        return fake.text(max_nb_chars=max_length)

                    if any(keyword in prop_name_lower for keyword in ['id', 'uuid']):
                        return str(uuid.uuid4())

                    actual_length = min(max_length, max(min_length, random.randint(5, 20)))
                    return ''.join(random.choices(string.ascii_letters + string.digits, k=actual_length))

                def generate_string(self, length: int = 10, pattern: str = None, default: str = None) -> str:
                    if default:
                        return default

                    if pattern:
                        if 'email' in pattern.lower():
                            return fake.email()
                        elif 'name' in pattern.lower():
                            return fake.name()
                        elif 'phone' in pattern.lower():
                            return fake.phone_number()
                        elif 'address' in pattern.lower():
                            return fake.address()
                        elif 'url' in pattern.lower():
                            return fake.url()
                        elif 'uuid' in pattern.lower():
                            return str(uuid.uuid4())

                    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

                def generate_integer(self, min_val: int = 1, max_val: int = 1000, default: int = None) -> int:
                    if default is not None:
                        return default
                    return random.randint(min_val, max_val)

                def generate_float(self, min_val: float = 0.0, max_val: float = 1000.0, default: float = None) -> float:
                    if default is not None:
                        return default
                    return round(random.uniform(min_val, max_val), 2)

                def generate_boolean(self, default: bool = None) -> bool:
                    if default is not None:
                        return default
                    return random.choice([True, False])

                def generate_id(self, prefix: str = "", id_type: str = "uuid") -> str:
                    if id_type == "uuid":
                        new_id = str(uuid.uuid4())
                    elif id_type == "incremental":
                        new_id = f"{len(self.generated_ids) + 1}"
                    else:
                        new_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

                    if prefix:
                        new_id = f"{prefix}_{new_id}"

                    self.generated_ids.add(new_id)
                    return new_id

                def generate_email(self) -> str:
                    return fake.email()

                def random_string(self, length: int = 10) -> str:
                    return ''.join(random.choices(string.ascii_letters, k=length))

                def random_int(self, min_val: int = 0, max_val: int = 1000) -> int:
                    return random.randint(min_val, max_val)

                def random_float(self, min_val: float = 0.0, max_val: float = 1000.0) -> float:
                    return random.uniform(min_val, max_val)

                def random_bool(self) -> bool:
                    return random.choice([True, False])

                def random_uuid(self) -> str:
                    return str(uuid.uuid4())

                def random_date(self, start_days_ago: int = 365, end_days_ahead: int = 365) -> str:
                    start_date = datetime.now() - timedelta(days=start_days_ago)
                    end_date = datetime.now() + timedelta(days=end_days_ahead)
                    return fake.date_between(start_date=start_date, end_date=end_date).isoformat()
            """
        )

        # Add global instance
        content += textwrap.dedent(
            """\


        # Global instance for easy access
        test_data_generator = TestDataGenerator()
        """
        )


        return content

    def _generate_config_file(self, api_info: Dict[str, Any]) -> str:
        """Generate config.py file content"""

        return textwrap.dedent(
            f"""\
        \"\"\"
        Configuration for Locust Load Tests
        Generated for: {api_info.get('title', 'API')}
        \"\"\"

        import os
        from dataclasses import dataclass
        from typing import Dict, List, Optional, Any
        from urllib.parse import urljoin
        from dotenv import load_dotenv

        load_dotenv()


        @dataclass
        class PerformanceThresholds:
            \"\"\"Performance thresholds for test validation\"\"\"
            max_response_time_ms: int = 2000  # Maximum acceptable response time
            max_95th_percentile_ms: int = 5000  # 95th percentile response time
            max_error_rate_percent: float = 1.0  # Maximum error rate percentage
            min_requests_per_second: float = 10.0  # Minimum RPS threshold


        @dataclass
        class LoadTestScenario:
            \"\"\"Load test scenario configuration\"\"\"
            name: str
            users: int
            spawn_rate: int
            run_time: str
            description: str


        class LoadTestConfig:
            \"\"\"Main configuration class for load tests\"\"\"

            def __init__(self):
                # API Configuration
                self.base_url = os.getenv('API_BASE_URL', '{api_info.get('base_url', 'http://localhost:8000')}')
                self.api_version = os.getenv('API_VERSION', '{api_info.get('version', 'v1')}')
                self.api_title = '{api_info.get('title', 'API')}'

                # Authentication
                self.api_key = os.getenv('API_KEY')
                self.auth_token = os.getenv('AUTH_TOKEN')
                self.username = os.getenv('API_USERNAME')
                self.password = os.getenv('API_PASSWORD')

                # Load Test Parameters
                self.users = int(os.getenv('LOCUST_USERS', '10'))
                self.spawn_rate = int(os.getenv('LOCUST_SPAWN_RATE', '2'))
                self.run_time = os.getenv('LOCUST_RUN_TIME', '5m')
                self.host = os.getenv('LOCUST_HOST', self.base_url)

                # Test Data Configuration
                self.use_realistic_data = os.getenv('USE_REALISTIC_DATA', 'true').lower() == 'true'
                self.data_seed = int(os.getenv('DATA_SEED', '42'))

                # Monitoring and Reporting
                self.enable_monitoring = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
                self.report_output_dir = os.getenv('REPORT_OUTPUT_DIR', './reports')
                self.log_level = os.getenv('LOG_LEVEL', 'INFO')

                # Performance Thresholds
                self.thresholds = PerformanceThresholds(
                    max_response_time_ms=int(os.getenv('MAX_RESPONSE_TIME_MS', '2000')),
                    max_95th_percentile_ms=int(os.getenv('MAX_95TH_PERCENTILE_MS', '5000')),
                    max_error_rate_percent=float(os.getenv('MAX_ERROR_RATE_PERCENT', '1.0')),
                    min_requests_per_second=float(os.getenv('MIN_REQUESTS_PER_SECOND', '10.0'))
                )

                # Test Scenarios
                self.scenarios = self._load_test_scenarios()

                # Request Configuration
                self.request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
                self.max_retries = int(os.getenv('MAX_RETRIES', '3'))

                # Load Balancing and Distribution
                self.enable_distributed = os.getenv('ENABLE_DISTRIBUTED', 'false').lower() == 'true'
                self.master_host = os.getenv('LOCUST_MASTER_HOST', 'localhost')
                self.master_port = int(os.getenv('LOCUST_MASTER_PORT', '5557'))


                # Feature Flags
                self.enable_custom_flows = os.getenv('ENABLE_CUSTOM_FLOWS', 'true').lower() == 'true'
                self.enable_response_validation = os.getenv('ENABLE_RESPONSE_VALIDATION', 'true').lower() == 'true'
                self.enable_performance_monitoring = os.getenv('ENABLE_PERF_MONITORING', 'true').lower() == 'true'

            def _load_test_scenarios(self) -> Dict[str, LoadTestScenario]:
                \"\"\"Load predefined test scenarios\"\"\"
                return {{
                    'smoke': LoadTestScenario(
                        name='Smoke Test',
                        users=5,
                        spawn_rate=1,
                        run_time='2m',
                        description='Quick smoke test to verify basic functionality'
                    ),
                    'load': LoadTestScenario(
                        name='Load Test',
                        users=50,
                        spawn_rate=5,
                        run_time='10m',
                        description='Standard load test with moderate user count'
                    ),
                    'stress': LoadTestScenario(
                        name='Stress Test',
                        users=200,
                        spawn_rate=10,
                        run_time='15m',
                        description='Stress test to find breaking points'
                    ),
                    'spike': LoadTestScenario(
                        name='Spike Test',
                        users=500,
                        spawn_rate=50,
                        run_time='5m',
                        description='Spike test with rapid user ramp-up'
                    ),
                    'soak': LoadTestScenario(
                        name='Soak Test',
                        users=100,
                        spawn_rate=5,
                        run_time='60m',
                        description='Long-running test to identify memory leaks'
                    )
                }}

            def get_scenario(self, scenario_name: str) -> Optional[LoadTestScenario]:
                \"\"\"Get specific test scenario\"\"\"
                return self.scenarios.get(scenario_name)

            def get_headers(self) -> Dict[str, str]:
                \"\"\"Get default headers for requests\"\"\"
                headers = {{
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': f'LoadTest/1.0'
                }}

                if self.api_key:
                    headers['X-API-Key'] = self.api_key

                if self.auth_token:
                    headers['Authorization'] = f'Bearer {{self.auth_token}}'

                return headers

            def get_full_url(self, path: str) -> str:
                \"\"\"Construct full URL from path\"\"\"
                return urljoin(self.base_url, path.lstrip('/'))

            def validate_config(self) -> List[str]:
                \"\"\"Validate configuration and return any errors\"\"\"
                errors = []

                if not self.base_url:
                    errors.append("Base URL is required")

                if self.users <= 0:
                    errors.append("User count must be positive")

                if self.spawn_rate <= 0:
                    errors.append("Spawn rate must be positive")

                if self.spawn_rate > self.users:
                    errors.append("Spawn rate cannot exceed user count")

                return errors


        # Global configuration instance
        config = LoadTestConfig()
        """
        )

    def _generate_utils_file(self) -> str:
        """Generate utils.py file content"""
        return textwrap.dedent(
            """\
        \"\"\"
        Utility classes for Locust load testing
        \"\"\"

        import json
        import logging
        import time
        from datetime import datetime
        from typing import Dict, List, Any, Optional
        from pathlib import Path
        import csv
        from dataclasses import dataclass, asdict
        import statistics
        from collections import defaultdict

        import requests
        from locust.runners import MasterRunner


        logger = logging.getLogger(__name__)


        @dataclass
        class ResponseMetric:
            \"\"\"Response metric data structure\"\"\"
            method: str
            endpoint: str
            response_time: float
            status_code: int
            response_size: int
            timestamp: datetime
            success: bool
            error_message: Optional[str] = None


        class ResponseValidator:
            \"\"\"Validates HTTP responses against expected criteria\"\"\"

            def __init__(self):
                self.validation_rules = {
                    'GET': {
                        'expected_status': [200, 202, 206],
                        'max_response_time_ms': 2000,
                        'required_headers': ['content-type'],
                        'forbidden_headers': ['x-debug', 'x-error-detail']
                    },
                    'POST': {
                        'expected_status': [200, 201, 202],
                        'max_response_time_ms': 3000,
                        'required_headers': ['content-type']
                    },
                    'PUT': {
                        'expected_status': [200, 202, 204],
                        'max_response_time_ms': 3000,
                        'required_headers': ['content-type']
                    },
                    'PATCH': {
                        'expected_status': [200, 202, 204],
                        'max_response_time_ms': 3000,
                        'required_headers': ['content-type']
                    },
                    'DELETE': {
                        'expected_status': [200, 202, 204],
                        'max_response_time_ms': 2000
                    }
                }

            def validate_response(self, response, method: str, endpoint: str) -> bool:
                \"\"\"Validate HTTP response against expected criteria\"\"\"
                is_valid = True
                method_upper = method.upper()
                rules = self.validation_rules.get(method_upper, {})

                # Validate status code
                expected_status = rules.get('expected_status', [200])
                if response.status_code not in expected_status:
                    logger.warning(f"Unexpected status code {response.status_code} for {method_upper} {endpoint}")
                    is_valid = False

                # Validate response time
                max_time = rules.get('max_response_time_ms', 5000)
                if response.elapsed.total_seconds() * 1000 > max_time:
                    logger.warning(f"Slow response {response.elapsed.total_seconds() * 1000:.2f}ms for {method_upper} {endpoint}")
                    is_valid = False

                # Check forbidden headers (security)
                forbidden_headers = rules.get('forbidden_headers', [])
                for header in forbidden_headers:
                    if header.lower() in [h.lower() for h in response.headers.keys()]:
                        logger.warning(f"Forbidden header '{header}' present for {method_upper} {endpoint}")
                        is_valid = False

                # Validate JSON response structure
                if response.status_code < 400 and 'application/json' in response.headers.get('content-type', ''):
                    try:
                        json_data = response.json()
                        if not self._validate_json_structure(json_data, method_upper, endpoint):
                            is_valid = False
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON response for {method_upper} {endpoint}")
                        is_valid = False

                return is_valid

            def _validate_json_structure(self, json_data: Any, method: str, endpoint: str) -> bool:
                \"\"\"Validate JSON response structure\"\"\"
                if method == 'GET' and isinstance(json_data, list):
                    if json_data and isinstance(json_data[0], dict):
                        return 'id' in json_data[0] or len(json_data[0]) > 0
                elif method in ['POST', 'PUT', 'PATCH'] and isinstance(json_data, dict):
                    return len(json_data) > 0
                return True

            def add_custom_validation(self, method: str, validation_func):
                \"\"\"Add custom validation function for specific method\"\"\"
                if not hasattr(self, 'custom_validators'):
                    self.custom_validators = {}
                self.custom_validators[method] = validation_func


        class RequestLogger:
            \"\"\"Logs HTTP requests for debugging and analysis\"\"\"

            def __init__(self, log_file: str = "requests.log"):
                self.log_file = log_file
                self.requests_logged = 0
                self.file_handler = logging.FileHandler(log_file)
                self.file_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                self.file_handler.setFormatter(formatter)

                self.request_logger = logging.getLogger('request_logger')
                self.request_logger.addHandler(self.file_handler)
                self.request_logger.setLevel(logging.INFO)

            @staticmethod
            def log_request(method: str, url: str, kwargs: Dict):
                logger.info(f"REQUEST: {method.upper()} {url}")
                if 'params' in kwargs and kwargs['params']:
                    logger.debug(f"Query params: {kwargs['params']}")
                if 'json' in kwargs and kwargs['json']:
                    logger.debug(f"JSON body: {json.dumps(kwargs['json'], indent=2)}")
                if 'data' in kwargs and kwargs['data']:
                    logger.debug(f"Form data: {kwargs['data']}")

            def log_response(self, response, method: str, url: str):
                self.requests_logged += 1
                log_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'method': method.upper(),
                    'url': url,
                    'status_code': response.status_code,
                    'response_time_ms': response.elapsed.total_seconds() * 1000,
                    'response_size': len(response.content) if response.content else 0
                }
                self.request_logger.info(json.dumps(log_entry))
                if response.status_code >= 400:
                    logger.error(f"ERROR RESPONSE: {response.status_code} for {method.upper()} {url}")
                    if response.text:
                        logger.error(f"Error details: {response.text[:500]}")


        class PerformanceMonitor:
            \"\"\"Monitors and reports performance metrics\"\"\"

            def __init__(self):
                self.metrics: List[ResponseMetric] = []
                self.start_time = None
                self.end_time = None
                self.request_counts = defaultdict(int)
                self.error_counts = defaultdict(int)

            def test_start(self):
                self.start_time = datetime.now()
                logger.info("Performance monitoring started")

            def test_stop(self):
                self.end_time = datetime.now()
                logger.info("Performance monitoring stopped")

            def record_response(self, response, method: str, endpoint: str):
                metric = ResponseMetric(
                    method=method.upper(),
                    endpoint=endpoint,
                    response_time=response.elapsed.total_seconds() * 1000,
                    status_code=response.status_code,
                    response_size=len(response.content) if response.content else 0,
                    timestamp=datetime.now(),
                    success=response.status_code < 400
                )
                if not metric.success:
                    metric.error_message = response.text[:200]
                self.metrics.append(metric)
                endpoint_key = f"{method.upper()} {endpoint}"
                self.request_counts[endpoint_key] += 1
                if not metric.success:
                    self.error_counts[endpoint_key] += 1

            def on_request_event(self, request_type, name, response_time, response_length, exception, context):
                if exception:
                    logger.error(f"Request failed: {request_type} {name} - {exception}")

            def get_statistics(self) -> Dict[str, Any]:
                if not self.metrics:
                    return {}
                response_times = [m.response_time for m in self.metrics]
                successful_requests = [m for m in self.metrics if m.success]
                stats = {
                    'total_requests': len(self.metrics),
                    'successful_requests': len(successful_requests),
                    'failed_requests': len(self.metrics) - len(successful_requests),
                    'error_rate': (len(self.metrics) - len(successful_requests)) / len(self.metrics) * 100,
                    'response_times': {
                        'min': min(response_times),
                        'max': max(response_times),
                        'mean': statistics.mean(response_times),
                        'median': statistics.median(response_times),
                        'p95': self._percentile(response_times, 95),
                        'p99': self._percentile(response_times, 99)
                    }
                }
                if self.start_time and self.end_time:
                    duration = (self.end_time - self.start_time).total_seconds()
                    stats['test_duration_seconds'] = duration
                    stats['requests_per_second'] = len(self.metrics) / duration
                stats['endpoints'] = self._get_endpoint_stats()
                return stats

            def _percentile(self, data: List[float], percentile: int) -> float:
                sorted_data = sorted(data)
                index = int((percentile / 100) * len(sorted_data))
                return sorted_data[min(index, len(sorted_data) - 1)]

            def _get_endpoint_stats(self) -> Dict[str, Dict]:
                endpoint_stats = {}
                for endpoint_key in self.request_counts.keys():
                    endpoint_metrics = [m for m in self.metrics if f"{m.method} {m.endpoint}" == endpoint_key]
                    if endpoint_metrics:
                        response_times = [m.response_time for m in endpoint_metrics]
                        successful = len([m for m in endpoint_metrics if m.success])
                        endpoint_stats[endpoint_key] = {
                            'total_requests': len(endpoint_metrics),
                            'successful_requests': successful,
                            'error_rate': (len(endpoint_metrics) - successful) / len(endpoint_metrics) * 100,
                            'avg_response_time': statistics.mean(response_times),
                            'p95_response_time': self._percentile(response_times, 95)
                        }
                return endpoint_stats

            def generate_report(self, output_dir: str = "./reports"):
                Path(output_dir).mkdir(exist_ok=True)
                stats = self.get_statistics()
                json_file = Path(output_dir) / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(json_file, 'w') as f:
                    json.dump(stats, f, indent=2, default=str)
                csv_file = Path(output_dir) / f"performance_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                with open(csv_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['timestamp', 'method', 'endpoint', 'response_time_ms', 'status_code', 'success'])
                    for metric in self.metrics:
                        writer.writerow([
                            metric.timestamp,
                            metric.method,
                            metric.endpoint,
                            metric.response_time,
                            metric.status_code,
                            metric.success
                        ])
                self._generate_summary_report(stats, output_dir)
                logger.info(f"Performance reports generated in {output_dir}")

            def _generate_summary_report(self, stats: Dict, output_dir: str):
                summary_file = Path(output_dir) / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(summary_file, 'w') as f:
                    f.write("PERFORMANCE TEST SUMMARY\\n")
                    f.write("=" * 50 + "\\n\\n")
                    f.write(f"Test Duration: {stats.get('test_duration_seconds', 0):.2f} seconds\\n")
                    f.write(f"Total Requests: {stats.get('total_requests', 0)}\\n")
                    f.write(f"Successful Requests: {stats.get('successful_requests', 0)}\\n")
                    f.write(f"Failed Requests: {stats.get('failed_requests', 0)}\\n")
                    f.write(f"Error Rate: {stats.get('error_rate', 0):.2f}%\\n")
                    f.write(f"Requests/Second: {stats.get('requests_per_second', 0):.2f}\\n\\n")
                    response_times = stats.get('response_times', {})
                    f.write("RESPONSE TIMES\\n")
                    f.write("-" * 20 + "\\n")
                    f.write(f"Min: {response_times.get('min', 0):.2f}ms\\n")
                    f.write(f"Max: {response_times.get('max', 0):.2f}ms\\n")
                    f.write(f"Mean: {response_times.get('mean', 0):.2f}ms\\n")
                    f.write(f"Median: {response_times.get('median', 0):.2f}ms\\n")
                    f.write(f"95th Percentile: {response_times.get('p95', 0):.2f}ms\\n")
                    f.write(f"99th Percentile: {response_times.get('p99', 0):.2f}ms\\n\\n")
                    endpoints = stats.get('endpoints', {})
                    if endpoints:
                        f.write("PER-ENDPOINT STATISTICS\\n")
                        f.write("-" * 30 + "\\n")
                        for endpoint, endpoint_stats in endpoints.items():
                            f.write(f"\\n{endpoint}:\\n")
                            f.write(f"  Requests: {endpoint_stats['total_requests']}\\n")
                            f.write(f"  Error Rate: {endpoint_stats['error_rate']:.2f}%\\n")
                            f.write(f"  Avg Response Time: {endpoint_stats['avg_response_time']:.2f}ms\\n")
                            f.write(f"  95th Percentile: {endpoint_stats['p95_response_time']:.2f}ms\\n")


        class DataManager:
            \"\"\"Manages test data and state across users\"\"\"

            def __init__(self):
                self.shared_data = {}
                self.user_data = {}

            def store_shared_data(self, key: str, value: Any):
                self.shared_data[key] = value

            def get_shared_data(self, key: str) -> Any:
                return self.shared_data.get(key)

            def store_user_data(self, user_id: str, key: str, value: Any):
                if user_id not in self.user_data:
                    self.user_data[user_id] = {}
                self.user_data[user_id][key] = value

            def get_user_data(self, user_id: str, key: str) -> Any:
                return self.user_data.get(user_id, {}).get(key)

            def cleanup_user_data(self, user_id: str):
                if user_id in self.user_data:
                    del self.user_data[user_id]


        # Global instances
        data_manager = DataManager()
        """
        )

    def _generate_custom_flows_file(self, endpoints: List[Endpoint]) -> str:
        """Generate custom_flows.py file content"""

        # Static base content (could later be enhanced using endpoints for auto flows)
        content = textwrap.dedent(
            """
        import random
        import time
        from typing import Dict, List, Any, Optional
        from locust import HttpUser, task, between, SequentialTaskSet
        import logging

        from test_data import TestDataGenerator
        from utils import ResponseValidator, data_manager

        logger = logging.getLogger(__name__)



        class APIWorkflowUser(HttpUser):
            \"\"\"User that executes complex workflows\"\"\"

            wait_time = between(2, 8)
            weight = 2

            tasks = []

            def on_start(self):
                self.workflow_data = {}
                logger.info("Workflow user started")

            def on_stop(self):
                logger.info("Workflow user stopped")


        class DataDependentFlow(SequentialTaskSet):
            \"\"\"Flow that demonstrates data dependencies between requests\"\"\"

            @task
            def create_resource(self):
                resource_data = {
                    'name': f"resource_{random.randint(1000, 9999)}",
                    'type': random.choice(['document', 'image', 'video']),
                    'metadata': {
                        'created_by': 'load_test',
                        'test_run': True
                    }
                }

                response_data = self.user.make_request(
                    method="post",
                    rile="/resources",
                    json=resource_data
                )

                if response_data and 'id' in response_data:
                    data_manager.store_shared_data('last_resource_id', response_data['id'])
                    self.user.user_data['resource_id'] = response_data['id']

            @task
            def update_resource(self):
                resource_id = self.user.user_data.get('resource_id') or data_manager.get_shared_data('last_resource_id')
                if resource_id:
                    update_data = {
                        'name': f"updated_resource_{random.randint(1000, 9999)}",
                        'status': 'active'
                    }
                    self.user.make_request(
                        method="put",
                        rile=f"/resources/{resource_id}",
                        json=update_data
                    )

            @task
            def get_resource(self):
                resource_id = self.user.user_data.get('resource_id')
                if resource_id:
                    self.user.make_request(
                        method="get",
                        rile=f"/resources/{resource_id}"
                    )

            @task
            def delete_resource(self):
                resource_id = self.user.user_data.get('resource_id')
                if resource_id:
                    self.user.make_request(
                        method="delete",
                        rile=f"/resources/{resource_id}"
                    )
                    self.user.user_data.pop('resource_id', None)




        class ComplexFlowUser(HttpUser):
            \"\"\"User that executes complex, realistic flows\"\"\"

            wait_time = between(3, 10)
            weight = 1

            tasks = [
                DataDependentFlow
            ]
        """
        )

        return content

    def _generate_requirements_file(self) -> str:
        """Generate requirements.txt file content"""
        return textwrap.dedent(
            """\
        # Core Locust dependencies
        locust>=2.15.0,<3.0.0

        # HTTP and API testing
        requests>=2.31.0
        urllib3>=1.26.0

        # Data generation and manipulation
        python-dateutil>=2.8.0

        # Data handling
        pandas>=2.0.0
        numpy>=1.24.0

        # Configuration and environment
        python-dotenv>=1.0.0
        pydantic>=2.0.0

        # Monitoring and reporting
        psutil>=5.9.0
        matplotlib>=3.7.0
        seaborn>=0.12.0

        # Logging and debugging
        structlog>=23.0.0
        colorama>=0.4.6
        Faker==37.6.0

        # Optional: Database connectivity
        # psycopg2-binary>=2.9.0  # PostgreSQL
        # pymongo>=4.3.0          # MongoDB
        """
        )

    def _generate_env_example(self) -> str:
        """Generate .env.example file content"""
        return textwrap.dedent(
            """\
            # =============================================================================
            # API Load Testing Configuration
            # =============================================================================
            # Copy this file to .env and configure your specific settings

            # API Configuration
            # =================
            API_BASE_URL=http://localhost:8000
            API_VERSION=v1
            API_TITLE=Your API Name

            # Authentication (choose one or more)
            # ===================================
            API_KEY=your_api_key_here
            AUTH_TOKEN=your_bearer_token_here
            API_USERNAME=your_username
            API_PASSWORD=your_password

            # OAuth2 Configuration (if applicable)
            OAUTH_CLIENT_ID=your_client_id
            OAUTH_CLIENT_SECRET=your_client_secret
            OAUTH_TOKEN_URL=https://your-auth-server.com/token

            # Load Test Parameters
            # ===================
            LOCUST_USERS=50
            LOCUST_SPAWN_RATE=5
            LOCUST_RUN_TIME=10m
            LOCUST_HOST=http://localhost:8000

            # Test Data Configuration
            # =======================
            USE_REALISTIC_DATA=true
            DATA_SEED=42
            REQUEST_TIMEOUT=30
            MAX_RETRIES=3

            # Test Behavior
            # =============
            ENABLE_CUSTOM_FLOWS=true
            ENABLE_RESPONSE_VALIDATION=true
            ENABLE_PERF_MONITORING=true
            ENABLE_REQUEST_LOGGING=true

            # Monitoring & Reporting
            # ======================
            REPORT_OUTPUT_DIR=./reports
            LOG_LEVEL=INFO
            ENABLE_MONITORING=true

            # Performance Thresholds (for automated pass/fail)
            # ================================================
            MAX_RESPONSE_TIME_MS=2000
            MAX_95TH_PERCENTILE_MS=5000
            MAX_ERROR_RATE_PERCENT=1.0
            MIN_REQUESTS_PER_SECOND=10.0

            # Response Size Limits
            MAX_RESPONSE_SIZE_MB=10
            MIN_RESPONSE_SIZE_BYTES=1

            # Distributed Testing Configuration
            # =================================
            ENABLE_DISTRIBUTED=false
            LOCUST_MASTER_HOST=localhost
            LOCUST_MASTER_PORT=5557
            LOCUST_WORKER_PORTS=5558,5559,5560

            # Database Configuration (for test data storage)
            # ==============================================
            # Uncomment if you need to store test data in a database
            # TEST_DB_URL=postgresql://user:pass@localhost/testdb
            # TEST_DB_POOL_SIZE=10
            # TEST_DB_MAX_OVERFLOW=20

            # Redis Configuration (for shared state)
            # ======================================
            # REDIS_URL=redis://localhost:6379/0
            # REDIS_PASSWORD=your_redis_password
            # REDIS_DB=0

            # External Integrations
            # ====================
            # Slack notifications for test results
            # SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK



            # Environment-Specific Settings
            # =============================
            ENVIRONMENT=development
            # Options: development, staging, production

            # Rate Limiting (to avoid overwhelming the API)
            # =============================================
            MAX_REQUESTS_PER_SECOND=100
            RATE_LIMIT_ENABLED=false

            # Security Settings
            # =================
            SSL_VERIFY=true
            TIMEOUT_CONNECT=10
            TIMEOUT_READ=30

            # Advanced Features
            # =================
            # Enable think time simulation (more realistic user behavior)
            ENABLE_THINK_TIME=true
            MIN_THINK_TIME=1
            MAX_THINK_TIME=5

            # Enable response caching for dependent requests
            ENABLE_RESPONSE_CACHING=true
            CACHE_TTL_SECONDS=300

            # Custom Headers (comma-separated key:value pairs)
            # CUSTOM_HEADERS=X-Client-Version:1.0,X-Request-Source:load-test

            # Debugging and Development
            # =========================
            DEBUG_MODE=false
            VERBOSE_LOGGING=false
            SAVE_REQUEST_RESPONSE_BODIES=false

            # Load Balancer Testing
            # =====================
            # LOAD_BALANCER_HOSTS=host1.example.com,host2.example.com,host3.example.com

            # Geographic Distribution Testing
            # ===============================
            # TEST_REGIONS=us-east-1,us-west-2,eu-west-1
            # REGION_WEIGHTS=50,30,20

            # Resource Monitoring
            # ===================
            MONITOR_SYSTEM_RESOURCES=true
            CPU_THRESHOLD_PERCENT=80
            MEMORY_THRESHOLD_PERCENT=80
            DISK_THRESHOLD_PERCENT=90

            # Test Data Cleanup
            # =================
            CLEANUP_TEST_DATA=true
            CLEANUP_ON_FAILURE=true
            PRESERVE_LAST_N_RUNS=5
        """
        )



    def _generate_readme_file(self, api_info: Dict[str, Any]) -> str:
        """Generate README.md file content"""
        return f"""# 🚀 Load Testing Suite for {api_info.get('title', 'API')}

    [![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
    [![Locust](https://img.shields.io/badge/locust-2.15+-green.svg)](https://locust.io/)
    [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

    Professional-grade performance testing suite for **{api_info.get('title', 'API')} {api_info.get('version', 'v1')}** built with Locust. This comprehensive toolkit provides realistic load testing scenarios, advanced monitoring, and detailed reporting capabilities.

    ## 📋 Table of Contents

    - [Quick Start](#-quick-start)
    - [Test Scenarios](#-test-scenarios)
    - [Configuration](#-configuration)
    - [Running Tests](#-running-tests)
    - [Monitoring & Reports](#-monitoring--reports)
    - [Custom Flows](#-custom-flows)
    - [Advanced Features](#-advanced-features)
    - [Troubleshooting](#-troubleshooting)
    - [Best Practices](#-best-practices)
    - [Contributing](#-contributing)

    ## 🚀 Quick Start

    ### Prerequisites

    - **Python 3.8+** with pip
    - **Network access** to the target API
    - **Minimum 2GB RAM** for load testing

    ### Installation

    ```bash
    # 1. Clone or download the test suite
    git clone <repository-url>
    cd load-testing-suite

    # 2. Install dependencies
    pip install -r requirements.txt

    # 3. Configure environment
    cp .env.example .env
    # Edit .env with your API configuration

    # 4. Run your first test
    locust -f locust.py
    ```


    ## 📊 Test Scenarios

    ### Built-in Scenarios

    | Scenario | Users | Spawn Rate | Duration | Purpose |
    |----------|-------|------------|----------|---------|
    | **🔍 smoke** | 5 | 1/sec | 2 min | Quick functionality verification |
    | **⚡ load** | 50 | 5/sec | 10 min | Standard load testing |
    | **💪 stress** | 200 | 10/sec | 15 min | Stress testing to find limits |
    | **🚀 spike** | 500 | 50/sec | 5 min | Spike testing with rapid ramp-up |
    | **🏃 soak** | 100 | 5/sec | 60 min | Long-running stability testing |
    | **⚙️ custom** | Variable | Variable | Variable | User-defined parameters |

    ### User Behavior Types

    The test suite simulates three types of users with different behavior patterns:

    - **🐌 LightUser (30%)** - Occasional usage, longer wait times (3-8s)
    - **👤 RegularUser (40%)** - Normal usage patterns, moderate wait times (1-4s)  
    - **💥 PowerUser (30%)** - Heavy usage, shorter wait times (0.5-2s), complex workflows

    ## 🔧 Configuration

    ### Environment Variables

    Create a `.env` file based on `.env.example`:

    ```bash
    # Core API Configuration
    API_BASE_URL=https://api.yourservice.com
    API_VERSION=v1
    API_KEY=your_secret_api_key

    # Test Parameters  
    LOCUST_USERS=50
    LOCUST_SPAWN_RATE=5
    LOCUST_RUN_TIME=10m

    # Features
    USE_REALISTIC_DATA=true
    ENABLE_MONITORING=true
    ENABLE_RESPONSE_VALIDATION=true

    # Performance Thresholds
    MAX_RESPONSE_TIME_MS=2000
    MAX_95TH_PERCENTILE_MS=5000
    MAX_ERROR_RATE_PERCENT=1.0
    ```

    ### Advanced Configuration

    Edit `config.py` to customize:

    ```python
    # Performance thresholds
    thresholds = PerformanceThresholds(
        max_response_time_ms=2000,
        max_95th_percentile_ms=5000,
        max_error_rate_percent=1.0,
        min_requests_per_second=10.0
    )

    # Custom test scenarios
    scenarios = {{
        'your_scenario': LoadTestScenario(
            name='Your Custom Test',
            users=75,
            spawn_rate=8,
            run_time='20m',
            description='Custom test description'
        )
    }}
    ```

    ## 🏃 Running Tests

    ### Command Line Interface

    ```bash
    # Quick tests
    ./run_tests.sh smoke                    # Smoke test
    ./run_tests.sh load                     # Standard load test
    ./run_tests.sh stress --monitor         # Stress test with system monitoring

    # Custom configurations
    ./run_tests.sh custom --users 100 --run-time 30m
    ./run_tests.sh load --host https://staging.api.com

    # With advanced options
    ./run_tests.sh stress \\
        --output ./results \\
        --csv performance_data \\
        --graphs \\
        --monitor

    # Web UI mode (interactive)
    ./run_tests.sh load --web-ui
    # Then open http://localhost:8089
    ```

    ### Distributed Testing

    For high-scale testing across multiple machines:

    ```bash
    # Master node
    ./run_tests.sh load --distributed

    # Worker nodes (run on separate machines)
    locust -f locustfile.py --worker --master-host=<master-ip>
    ```

    ## 📈 Monitoring & Reports

    ### Real-time Monitoring

    - **📊 Web Dashboard**: http://localhost:8089 (when using `--web-ui`)
    - **🔍 Response Validation**: Automatic validation of response codes, times, and structure
    - **📱 System Metrics**: CPU, memory, and disk usage monitoring (with `--monitor`)
    - **📋 Request Logging**: Detailed request/response logging for debugging

    ### Generated Reports

    After test completion, find reports in the `./reports/` directory:

    #### HTML Dashboard
    - **`report_SCENARIO_TIMESTAMP.html`** - Interactive dashboard with:
      - Response time charts and percentiles
      - Request distribution graphs  
      - Error rate analysis
      - Endpoint performance breakdown

    #### Data Files
    - **`performance_report_TIMESTAMP.json`** - Machine-readable metrics
    - **`performance_metrics_TIMESTAMP.csv`** - Raw data for custom analysis
    - **`summary_TIMESTAMP.txt`** - Human-readable summary

    #### Sample Summary Report

    ```
    PERFORMANCE TEST SUMMARY
    ==================================================

    Test Duration: 600.00 seconds
    Total Requests: 15,247
    Successful Requests: 15,162
    Failed Requests: 85
    Error Rate: 0.56%
    Requests/Second: 25.41

    RESPONSE TIMES
    --------------------
    Min: 23.45ms
    Max: 2,156.78ms
    Mean: 145.23ms  
    Median: 128.56ms
    95th Percentile: 267.89ms
    99th Percentile: 456.12ms

    PER-ENDPOINT STATISTICS
    ------------------------------

    GET /api/users:
      Requests: 5,421
      Error Rate: 0.12%  
      Avg Response Time: 98.45ms
      95th Percentile: 189.23ms

    POST /api/orders:
      Requests: 3,128
      Error Rate: 1.23%
      Avg Response Time: 234.56ms
      95th Percentile: 445.67ms
    ```

    ### Performance Thresholds

    Tests automatically validate against configured thresholds:

    ```bash
    ✅ Response Time: 145ms (threshold: 2000ms)
    ✅ 95th Percentile: 267ms (threshold: 5000ms)  
    ✅ Error Rate: 0.56% (threshold: 1.0%)
    ❌ RPS: 8.5 (threshold: 10.0) - FAILED
    ```

    ## 🔄 Custom Flows

    ### Built-in Complex Workflows

    #### 1. User Registration Flow
    ```python
    # Simulates complete user onboarding
    - Register new user account
    - Verify email address  
    - Complete user profile
    - Fetch user data
    ```

    #### 2. E-commerce Shopping Flow  
    ```python
    # Realistic shopping experience
    - Browse product catalog
    - View product details and reviews
    - Add items to shopping cart
    - Apply discount coupons
    - Complete checkout process
    ```

    #### 3. Content Management Flow
    ```python
    # Content lifecycle testing
    - Create new content items
    - Update existing content
    - Publish content
    - Search and retrieve content
    ```

    ### Creating Custom Flows

    Add your own workflows in `custom_flows.py`:

    ```python
    class MyBusinessFlow(SequentialTaskSet):
        \"\"\"Custom business workflow\"\"\"

        @task
        def step_1_authenticate(self):
            response = self.user.make_request(
                method="post",
                rile="/auth/login",
                json={{"username": "test_user", "password": "secret"}}
            )
            if response and 'token' in response:
                self.user.auth_token = response['token']

        @task  
        def step_2_fetch_data(self):
            self.user.make_request(
                method="get",
                path="/api/dashboard/data"
            )

        @task
        def step_3_process_data(self):
            # Your custom logic here
            pass
    ```

    ### Data Dependencies

    Handle dependent requests with shared data:

    ```python
    # Store data for later use
    self.user._store_response_data("user_creation", response_data)

    # Retrieve stored data
    user_id = self.user.user_data.get("user_creation", {{}}).get("id")

    # Use shared data across users
    data_manager.store_shared_data("global_config", config_data)
    ```

    ## 🔥 Advanced Features

    ### 1. Response Validation

    Automatic validation includes:
    - ✅ HTTP status codes
    - ✅ Response time thresholds  
    - ✅ Required headers presence
    - ✅ JSON structure validation
    - ✅ Security header checks

    ### 2. Realistic Data Generation

    Powered by Faker library:
    ```python
    # Generates realistic test data
    - Names, emails, addresses
    - Product information
    - Financial data
    - Geographic data
    - Custom patterns and schemas
    ```

    ### 3. Error Scenario Testing

    Built-in error handling tests:
    - Invalid request data
    - Non-existent resources
    - Authentication failures  
    - Rate limiting scenarios
    - Network timeout simulation

    ### 4. Performance Monitoring

    System resource tracking:
    ```bash
    # Enable with --monitor flag
    CPU Usage: 45.2%
    Memory: 2.1GB / 8GB (26%)
    Disk I/O: 45 MB/s read, 12 MB/s write
    Network: 15 Mbps in, 8 Mbps out
    ```

    ### 5. Load Balancer Testing

    Test multiple backend servers:
    ```bash
    # Configure multiple hosts
    LOAD_BALANCER_HOSTS=api1.example.com,api2.example.com,api3.example.com
    ```

    ## 🐛 Troubleshooting

    ### Common Issues and Solutions

    #### Connection Errors
    ```bash
    # Problem: "Connection refused" errors
    # Solutions:
    1. Verify API_BASE_URL in .env file
    2. Check if API server is running and accessible
    3. Validate network connectivity: curl $API_BASE_URL/health
    4. Check firewall and security group settings
    ```

    #### High Error Rates
    ```bash
    # Problem: Error rate > 5%
    # Solutions:  
    1. Check API rate limiting configuration
    2. Verify authentication credentials are valid
    3. Review request data formats and required fields
    4. Monitor API server resources and logs
    5. Reduce load (lower user count or spawn rate)
    ```

    #### Slow Performance
    ```bash
    # Problem: Response times > thresholds
    # Solutions:
    1. Monitor API server CPU/memory usage
    2. Check database connection pool settings
    3. Review network latency between test and API
    4. Optimize API queries and caching
    5. Scale API infrastructure if needed
    ```

    #### Memory Issues
    ```bash
    # Problem: "Out of memory" errors during test
    # Solutions:
    1. Reduce number of concurrent users
    2. Enable data cleanup: CLEANUP_TEST_DATA=true
    3. Increase system memory or use distributed testing
    4. Monitor test client resource usage
    ```

    ### Debug Mode

    Enable detailed debugging:

    ```bash
    # Environment variable
    export LOG_LEVEL=DEBUG

    # Command line
    ./run_tests.sh load --log-level DEBUG

    # Check logs
    tail -f requests.log
    ```

    ### Validation Scripts

    Run validation before main tests:

    ```bash
    # Test API connectivity
    curl -I $API_BASE_URL/health

    # Validate authentication  
    ./validate_auth.py

    # Check test data generation
    python3 -c "from test_data import TestDataGenerator; print(TestDataGenerator().generate_realistic_user_data())"
    ```

    ## 💡 Best Practices

    ### Test Design

    1. **Start Small**: Begin with smoke tests before running full load tests
    2. **Realistic Data**: Use representative test data, not hardcoded values
    3. **Think Time**: Include realistic wait times between requests
    4. **Error Testing**: Test both success and failure scenarios
    5. **Incremental Load**: Gradually increase load to find breaking points

    ### Environment Management

    1. **Separate Environments**: Never run load tests against production
    2. **Consistent Infrastructure**: Use production-like test environments
    3. **Data Isolation**: Use separate test databases and services
    4. **Clean State**: Reset environment between major test runs

    ### Monitoring and Analysis

    1. **Baseline Metrics**: Establish performance baselines
    2. **Trend Analysis**: Track performance over time
    3. **Both Sides**: Monitor both client and server metrics
    4. **Business Context**: Relate technical metrics to business impact

    ### Team Collaboration

    1. **Shared Results**: Store reports in accessible locations
    2. **Documentation**: Keep test scenarios and rationale documented
    3. **CI Integration**: Automate tests in deployment pipelines
    4. **Threshold Management**: Regularly review and update thresholds

    ## 🔒 Security Considerations

    ### Authentication & Authorization
    - ✅ Support for multiple auth methods (API keys, OAuth, JWT)
    - ✅ Secure credential storage in environment variables
    - ✅ Session management for stateful authentication
    - ✅ Role-based access testing

    ### Data Privacy
    - ✅ Synthetic data generation (no real user data)
    - ✅ Configurable data patterns for compliance
    - ✅ Automatic data cleanup after tests
    - ✅ No sensitive data in logs or reports

    ### Infrastructure Security
    - ✅ Network isolation for test environments
    - ✅ Encrypted connections (HTTPS/TLS)
    - ✅ Rate limiting respect and testing
    - ✅ Resource exhaustion protection

    ## 📚 API Reference

    ### Environment Variables

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `API_BASE_URL` | `http://localhost:8000` | Target API base URL |
    | `API_KEY` | - | API authentication key |
    | `LOCUST_USERS` | `50` | Number of simulated users |
    | `LOCUST_SPAWN_RATE` | `5` | Users spawned per second |
    | `LOCUST_RUN_TIME` | `10m` | Test duration |
    | `MAX_RESPONSE_TIME_MS` | `2000` | Response time threshold |
    | `MAX_ERROR_RATE_PERCENT` | `1.0` | Error rate threshold |
    | `USE_REALISTIC_DATA` | `true` | Enable realistic data generation |

    ### Command Line Options

    ```bash
    ./run_tests.sh [SCENARIO] [OPTIONS]

    Scenarios: smoke, load, stress, spike, soak, custom

    Options:
      -h, --help              Show help message
      -w, --web-ui           Enable interactive web UI
      -o, --output DIR       Report output directory
      -l, --log-level LEVEL  Logging level (DEBUG, INFO, WARN, ERROR)
      -d, --distributed      Enable distributed testing mode
      -c, --csv FILE         Export CSV data
      --monitor              Monitor system resources
      --graphs               Generate performance graphs
      --dry-run              Validate without running
      --quiet                Suppress non-essential output
    ```


    **Generated by DevDox AI Context - Locust Test Generator**

    | Info | Value |
    |------|-------|
    | **API** | {api_info.get('title', 'Unknown')} v{api_info.get('version', '1.0')} |
    | **Generated** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
    | **Base URL** | {api_info.get('base_url', 'http://localhost:8000')} |

    > 💡 **Pro Tip**: Start with the `smoke` scenario to verify everything works, then gradually increase load with `load` and `stress` scenarios.
    """
