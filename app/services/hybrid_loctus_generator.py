"""
Hybrid Locust Test Generator

Combines reliable template-based generation with LLM enhancement for creativity
and domain-specific optimizations.
"""

import json
import os
import re
import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
import uuid
import shutil


from app.handlers.utils.open_ai_parser import (
    Endpoint,
    Parameter,
    RequestBody,
    Response,
    ParameterType,
)
from app.services.locust_generator import LocustTestGenerator, TestDataConfig

logger = logging.getLogger(__name__)


@dataclass
class AIEnhancementConfig:
    """Configuration for AI enhancement"""

    model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    max_tokens: int = 8000
    temperature: float = 0.3
    timeout: int = 60
    enhance_workflows: bool = True
    enhance_test_data: bool = False
    enhance_validation: bool = False
    create_domain_flows: bool = True
    update_main_locust: bool = True


@dataclass
class EnhancementResult:
    """Result of AI enhancement"""

    success: bool
    enhanced_files: Dict[str, str]
    enhanced_directory_files  :List[Dict[str, Any]]
    enhancements_applied: List[str]
    errors: List[str]
    processing_time: float


class HybridLocustGenerator:
    """
    Hybrid generator that combines template-based reliability with AI creativity
    """

    def __init__(
        self,
        ai_client=None,
        ai_config: AIEnhancementConfig = None,
        test_config: TestDataConfig = None,
    ):
        self.ai_client = ai_client
        self.ai_config = ai_config or AIEnhancementConfig()
        self.template_generator = LocustTestGenerator(test_config)
        self.enhancement_cache = {}

    async def generate_from_endpoints(
        self,
        endpoints: List[Endpoint],
        api_info: Dict[str, Any],
        output_dir: str = "locust_tests",
    ) -> Dict[str, str]:
        """
        Generate Locust tests using hybrid approach

        1. Generate reliable base structure with templates
        2. Enhance with AI for domain-specific improvements
        3. Validate and merge results
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Step 1: Generate reliable base structure
            logger.info("🔧 Generating base test structure with templates...")
            base_files, directory_files, grouped_enpoints = self.template_generator.generate_from_endpoints(
                endpoints, api_info, output_dir
            )

            #directory_files = self.template_generator.fix_indent(directory_files)
            base_files = self.template_generator.fix_indent(base_files)

            # Step 2: Enhance with AI if available
            if self.ai_client and self._should_enhance(endpoints, api_info):

                logger.info("🤖 Enhancing tests with AI...")
                enhancement_result = await self._enhance_with_ai(
                    base_files, endpoints, api_info, directory_files, grouped_enpoints
                )

                if enhancement_result.success:
                    logger.info(
                        f"✅ AI enhancements applied: {', '.join(enhancement_result.enhancements_applied)}"
                    )
                    return enhancement_result.enhanced_files, enhancement_result.enhanced_directory_files
                else:
                    logger.warning(
                        f"⚠️ AI enhancement failed, using template base: {', '.join(enhancement_result.errors)}"
                    )
            else:
                logger.info("📋 Using template-based generation only")

            processing_time = asyncio.get_event_loop().time() - start_time
            logger.info(f"⏱️ Generation completed in {processing_time:.2f}s")

            return base_files,directory_files

        except Exception as e:
            logger.error(f"Hybrid generation failed: {e}")
            # Fallback to template-only
            return self.template_generator.generate_from_endpoints(
                endpoints, api_info, output_dir
            ),[]

    def _should_enhance(
        self, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> bool:
        """Determine if AI enhancement is worthwhile"""
        # Enhance if we have enough endpoints or complex schemas
        complex_endpoints = [
            ep
            for ep in endpoints
            if ep.request_body or len(ep.parameters) > 3 or len(ep.responses) > 2
        ]

        return (
            len(endpoints) >= 3
            or len(complex_endpoints)  # Enough endpoints for meaningful enhancement
            >= 1
            or self._detect_domain_patterns(  # Has complex endpoints
                endpoints, api_info
            )  # Has recognizable domain patterns
        )

    def _detect_domain_patterns(
        self, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> bool:
        """Detect if API belongs to known domains that benefit from custom flows"""
        domain_keywords = {
            "ecommerce": ["product", "cart", "order", "payment", "checkout"],
            "user_management": ["user", "auth", "login", "register", "profile"],
            "content_management": ["post", "article", "comment", "media", "upload"],
            "financial": ["transaction", "account", "balance", "transfer"],
            "social": ["friend", "follow", "message", "notification", "feed"],
        }

        api_text = f"{api_info.get('title', '')} {api_info.get('description', '')}"
        endpoint_paths = " ".join([ep.path for ep in endpoints])
        combined_text = f"{api_text} {endpoint_paths}".lower()

        for domain, keywords in domain_keywords.items():
            if any(keyword in combined_text for keyword in keywords):
                return True

        return False

    def _split_content_into_chunks(self, content: str, chunk_size: int, overlap_size: int) -> List[str]:
        """Split content into overlapping chunks using LangChain's RecursiveCharacterTextSplitter"""
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        if len(content) <= chunk_size:
            return [content]

        # Define Python-specific separators for better code splitting
        python_separators = [
            "\n\nclass ",  # Class definitions
            "\n\ndef ",  # Function definitions
            "\n\nasync def ",  # Async function definitions
            "\n\n",  # Double newlines (logical breaks)
            "\n",  # Single newlines
            " ",  # Spaces
            ""  # Character level (fallback)
        ]

        # Initialize the text splitter with Python-optimized settings
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap_size,
            length_function=len,
            separators=python_separators,
            keep_separator=True,  # Keep separators to maintain code structure
            is_separator_regex=False
        )

        try:
            # Split the content
            chunks = text_splitter.split_text(content)

            return chunks

        except Exception as e:

            # Fallback to simple splitting if LangChain fails
            return self._simple_split_fallback(content, chunk_size, overlap_size)

    def _simple_split_fallback(self, content: str, chunk_size: int, overlap_size: int) -> List[str]:
        """Fallback simple splitting method"""
        chunks = []
        start = 0

        while start < len(content):
            end = start + chunk_size

            # If this isn't the last chunk, try to break at a logical point
            if end < len(content):
                # Look for good break points (end of line, end of function/class)
                break_point = content.rfind('\n', start, end)
                if break_point > start + chunk_size // 2:
                    end = break_point + 1

            chunk = content[start:end]
            chunks.append(chunk)

            # Move start position (with overlap)
            if end >= len(content):
                break
            start = end - overlap_size

        return chunks


    def _format_conversation_history(self, history: List[Dict]) -> str:
        """Format conversation history for context"""
        if not history:
            return ""

        formatted = []
        for item in history:
            formatted.append(f"Chunk {item['chunk_number']}: Enhanced successfully")

        return "\n".join(formatted[-3:])  # Only keep last 3 for brevity

    def _merge_chunks(self, chunks: List[str], overlap_size: int) -> str:
        """Merge enhanced chunks back together, removing overlaps"""
        if not chunks:
            return ""

        if len(chunks) == 1:
            return chunks[0]

        merged = chunks[0]

        for i in range(1, len(chunks)):
            current_chunk = chunks[i]

            # Simple overlap removal - remove first overlap_size characters from current chunk
            if len(current_chunk) > overlap_size:
                # Try to find a good merge point (start of new line)
                merge_point = current_chunk.find('\n', overlap_size // 2)
                if merge_point > 0:
                    current_chunk = current_chunk[merge_point + 1:]
                else:
                    current_chunk = current_chunk[overlap_size:]

            merged += current_chunk

        return merged

    async def _enhance_locustfile(
            self, base_content: str, endpoints: List[Any], api_info: Dict[str, Any]
    ) -> Optional[str]:
        # Configuration
        try:


            # Merge all enhanced chunks back together

            prompt = f"""Enhance this Locust test file to be more professional and realistic and fix the indentation issues:

               ```python
               {base_content}
               ```

               Available Endpoints: {self._format_endpoints_for_prompt(endpoints[:5])}
               API Info: {api_info.get('title', 'API')} v{api_info.get('version', '1.0')}

               Fix ONLY the formatting and indentation issues in this Locust test file. 

                STRICT REQUIREMENTS:
                - Fix indentation and formatting ONLY
                - Do NOT add new tasks, methods, or endpoints
                - Do NOT modify existing task logic
                - Do NOT add new functionality
                - Keep the exact same tasks and methods
                - Only fix Python syntax, imports, and indentation

              Always return your code wrapped in <code></code> tags with no explanations outside the tags DO NOT TRUNCATE THE CODE. 
              IMPORTANT: Return the SAME code with ONLY formatting fixes. Do not enhance or add anything
              Format: <code>your_python_code_here</code>:"""

            try:

                enhanced_content = await self._call_ai_service(prompt)
                return enhanced_content
            except Exception as e:
                logger.error(f"Enhancement failed: {e}")
                return base_content

        except Exception as e:
            logger.error(f"Locustfile enhancement failed: {e}")

            return base_content


    async def _enhance_with_ai(
        self,
        base_files: Dict[str, str],

        endpoints: List[Endpoint],
        api_info: Dict[str, Any],
        directory_files:   List[Dict[str, Any]],
        grouped_enpoints:  Dict[str, List[Endpoint]]
    ) -> EnhancementResult:
        """Enhance base files with AI"""
        start_time = asyncio.get_event_loop().time()
        enhanced_files = base_files.copy()
        enhanced_directory_files = []
        enhancements_applied = []
        errors = []
        try:
            if self.ai_config.update_main_locust:
                enhanced_files['locustfile.py'] = await self._enhance_locustfile(
                    base_files.get("locustfile.py", ""), endpoints, api_info
                )


            # Enhancement 1: Domain-specific user flows
            if self.ai_config.create_domain_flows:
                domain_flows = await self._generate_domain_flows(endpoints, api_info)
                if domain_flows:
                    enhanced_files["custom_flows.py"] = domain_flows
                    enhancements_applied.append("domain_flows")
                    print("enhanced custom_flows file")

            # Enhancement 2: Enhanced custom workflows
            if self.ai_config.enhance_workflows:
                base_workflow_files = self.get_files_by_key(directory_files, 'base_workflow.py')

                for items in directory_files:
                    for key, value in items.items():

                        enhanced_workflow = await self._enhance_workflows(
                            value, endpoints, api_info, base_files.get("test_data.py", ""), base_workflow_files, grouped_enpoints.get(key.replace("_workflow.py",""))
                        )
                        if enhanced_workflow:
                            enhanced_directory_files.append({key: enhanced_workflow})
                            print(f"enhanced_workflows_{key}")
                            enhancements_applied.append(f"enhanced_workflows_{key}")

            # Enhancement 3: Smart test data generation
            if self.ai_config.enhance_test_data:
                enhanced_test_data = await self._enhance_test_data(
                    base_files.get("test_data.py", ""), endpoints, api_info
                )
                if enhanced_test_data:
                    enhanced_files["test_data.py"] = enhanced_test_data
                    enhancements_applied.append("smart_test_data")


            # Enhancement 4: Advanced response validation
            if self.ai_config.enhance_validation:
                enhanced_validation = await self._enhance_validation(
                    base_files.get("utils.py", ""), endpoints, api_info
                )
                if enhanced_validation:
                    enhanced_files["utils.py"] = enhanced_validation
                    enhancements_applied.append("advanced_validation")

            processing_time = asyncio.get_event_loop().time() - start_time

            return EnhancementResult(
                success=True,
                enhanced_files=enhanced_files,
                enhanced_directory_files=enhanced_directory_files,
                enhancements_applied=enhancements_applied,
                errors=errors,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"AI enhancement failed: {e}")

            processing_time = asyncio.get_event_loop().time() - start_time

            return EnhancementResult(
                success=False,
                enhanced_files=base_files,
                enhancements_applied=[],
                enhanced_directory_files=[],
                errors=[str(e)],
                processing_time=processing_time,
            )

    async def _generate_domain_flows(
        self, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> Optional[str]:
        """Generate domain-specific user flows"""

        # Analyze endpoints to determine domain
        domain_analysis = self._analyze_api_domain(endpoints, api_info)

        prompt = f"""Based on this API analysis, create domain-specific user flows for Locust testing:

API Analysis:
{domain_analysis}

Endpoints Available:
{self._format_endpoints_for_prompt(endpoints)}  # Limit for token efficiency

Generate a Python file with domain-specific user flow classes that extend the base CustomUserFlow.
Focus on realistic business workflows that users would actually perform.

Requirements:
1. Create 2-3 domain-specific flow classes
2. Use sequential tasks for related API calls and use coorelation between them
3. To check payload and update it if it is not valid
4. Each flow should represent a complete business process
5. Include proper error handling and realistic wait times
6. Use the available endpoints in logical sequences
7. Add meaningful logging and data tracking

Always return your code wrapped in <code></code> tags with no explanations outside the tags DO NOT TRUNCATE THE CODE. 
IMPORTANT: Return the SAME code with ONLY formatting fixes. Do not enhance or add anything
Format: <code>your_python_code_here</code>"""
        print("prompt line 453")
        print(prompt)
        try:
            enhanced_content = await self._call_ai_service(prompt)
            print("enhanced_content ", enhanced_content)
            if enhanced_content :
                return enhanced_content
        except Exception as e:
            logger.warning(f"Domain flows generation failed: {e}")

        return ""

    def get_files_by_key(self,directory_files, target_key):
        """Return directory items that contain the specified key"""
        return [items for items in directory_files if target_key in items]


    async def _enhance_workflows(
        self, base_content: str, endpoints: List[Endpoint], api_info: Dict[str, Any], test_data_content: str,base_workflow:str, grouped_enpoints: Dict[str, List[Endpoint]]
    ) -> Optional[str]:

        """Enhance existing workflows with AI"""

        prompt = f"""CRITICAL CONSTRAINTS: Only use endpoints that exist in the OpenAPI specification. DO NOT create, modify, or reference any endpoints not listed below. 
        TASK: Enhance this Locust workflow file with realistic load testing patterns and LOGICAL TASK ORDERING.
        STRICT REQUIREMENTS:
        1. ONLY use these exact API endpoints from OpenAPI spec:
        {grouped_enpoints}
         2. PRESERVE EXISTING STRUCTURE:
           - Keep ALL existing @task methods, classes, and functions
           - DO NOT remove any existing functionality
           - DO NOT change existing method signatures unless enhancing them
           - ADD to existing methods, don't replace them
       3. ADD NEW FUNCTIONALITY WHEN NEEDED:
           - If an API endpoint requires specific IDs, ADD new methods to generate/store those IDs
           - ADD new test data generators to test_data.py functions
           - ADD new example usage patterns to example.py
           - CREATE data flow between related API calls

    4. DATA FLOW AND ID MANAGEMENT:
       - ADD instance variables to store IDs (self.reseller_id, self.user_id, etc.)
       - ADD methods to extract and store IDs from API responses
       - ADD logic to use stored IDs in subsequent API calls
       - CREATE realistic data dependencies between tasks

    5. ENHANCEMENT AREAS (ADD, don't replace):
       - ADD better error handling to existing methods
       - ADD realistic test data usage from test_data.py
       - ADD authentication handling if auth endpoints exist
       - ADD cleanup methods for created resources
       - ADD data correlation between sequential tasks

        
        CURRENT WORKFLOW FILE:
        {base_content}
        
        BASE WORKFLOW: {base_workflow}

        TEST DATA AVAILABLE: {test_data_content}
        1. **REORDER TASKS FOR LOGICAL FLOW**: Arrange @task methods in a meaningful business workflow sequence:

   - Start with data creation tasks (e.g., add_reseller)

   - Follow with data retrieval to get IDs for subsequent operations (e.g., get_reseller, get_reseller_by_id)

   - Then perform operations using those IDs (e.g., customize_corporate_price, available_reseller_properties)

   - End with cleanup operations (e.g., delete_reseller)



2. **DATA CORRELATION**: Use data from previous tasks in subsequent tasks:

   - Store reseller IDs from add_reseller for use in get_reseller_by_id, customize_price, etc.

   - Pass generated data between related API calls

   - Maintain state between sequential tasks for realistic workflows

3. Fix indentation issues


4. **Test Data Enhancement** (if needed, suggest additions):
       If APIs need specific data formats, suggest:
       - New functions to add to test_data.py
       - New example patterns to add to example.py
       - New data generators for specific ID requirements



5. Use realistic functions and classes from base_workflow.py and don't remove classes or functions from this file

6. Add intelligent request chaining between related API calls

7. Add authentication handling ONLY if auth endpoints exist in OpenAPI spec

8. Add error recovery for existing methods

9. Add data cleanup on stop for resources created during testing

10. Improve data parameterization using available test data generators



LOGICAL TASK SEQUENCE EXAMPLE:

For reseller workflow, the logical order should be:

1. add_reseller (create) → store reseller_id

2. get_reseller (list/search) 

3. get_reseller_by_id (using stored reseller_id)

4. available_reseller_properties (using reseller_id)

5. customize_corporate_price (using reseller_id)

6. customize_corporate_price_csv (using reseller_id)

7. customize_price (using reseller_id)

8. customize_price_csv (using reseller_id)

9. topup_reseller_balance (using reseller_id)

10. edit_reseller (using reseller_id)

11. delete_reseller (cleanup using reseller_id)

VALIDATION RULES:
    - Every @task method must correspond to an actual OpenAPI endpoint
    - PRESERVE all existing functionality
    - ADD new functionality only where needed for data flow
    - Use only test_data.py functions that exist or suggest new ones to ADD
    - Ensure realistic user workflows with proper data dependencies
    - ADD error handling and resource cleanup

    SUGGESTIONS FOR ADDITIONS (if needed):
    If the workflow needs new test data generators or example patterns, 
    provide suggestions for what to ADD to:
    
    test_data.py additions:
    ```python
    # Suggest new functions to ADD (don't replace existing)
    def get_specific_id_data():
        # New function for ID-dependent APIs
        pass
    ```
    
    example.py additions:
    ```python
    # Suggest new example patterns to ADD
    def example_id_workflow():
        # New example showing ID usage
        pass
    ```

    Return the complete enhanced file in <code></code> tags without truncation.
    If you suggest additions to test_data.py or example.py, include them after the main code.
    
    Format: 
    <code>your_complete_enhanced_python_code_here</code>
    
    SUGGESTED_ADDITIONS_FOR_test_data.py:
    <code_test_data>suggested_new_test_data_functions</code_test_data>
    
    SUGGESTED_ADDITIONS_FOR_example.py:
    <code_example>suggested_new_example_patterns</code_example>"""

        try:

            enhanced_content = await self._call_ai_service(prompt)

            return enhanced_content
        except Exception as e:
            logger.warning(f"Workflow enhancement failed: {e}")

        return ""

    async def _enhance_test_data(
        self, base_content: str, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> Optional[str]:
        """Enhance test data generation with domain knowledge"""

        # Extract schema information
        schemas_info = self._extract_schema_patterns(endpoints)

        prompt = f"""Enhance this test data generator with domain-specific realistic data:

Current File:
{base_content}...

API Schemas Found:
{schemas_info}

Enhance by:
1. Adding domain-specific data generators (based on field names and types)
2. Creating realistic data relationships 
3. Keep same parameteres of functions and method as it may be called by other files
4. Adding data validation and constraints
5. Add coorelation between related API calls
6. Implementing smart data caching for performance
7. Adding specialized generators for common patterns

Keep existing methods but make them smarter and more realistic.
Output: Complete enhanced Python file content."""

        try:
            enhanced_content = await self._call_ai_service(prompt)
            if enhanced_content and self._validate_python_code(enhanced_content):
                return enhanced_content
        except Exception as e:
            logger.warning(f"Test data enhancement failed: {e}")

        return ""

    async def _enhance_validation(
        self, base_content: str, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> Optional[str]:
        """Enhance response validation with endpoint-specific checks"""

        validation_patterns = self._extract_validation_patterns(endpoints)

        prompt = f"""Enhance this utils file with smarter response validation:

Current File:
{base_content}...

Validation Patterns Needed:
{validation_patterns}

Enhance by:
1. Adding endpoint-specific validation rules
2. Creating schema-based response validation
3. Adding business logic validation
4. Implementing response data integrity checks
5. Adding performance threshold validation

Keep existing utility functions but add smarter validation logic.
Output: Complete enhanced Python file content."""

        try:
            enhanced_content = await self._call_ai_service(prompt)
            if enhanced_content :
                return enhanced_content
        except Exception as e:
            logger.warning(f"Validation enhancement failed: {e}")

        return ""

    async def _generate_performance_scenarios(
        self, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> Optional[str]:
        """Generate performance testing scenarios"""

        performance_analysis = self._analyze_performance_patterns(endpoints)

        prompt = f"""Create performance testing scenarios for this API:

API: {api_info.get('title', 'Unknown API')}
Performance Analysis:
{performance_analysis}

Create a Python file with specialized performance testing scenarios:
1. Spike testing scenarios
2. Stress testing patterns
3. Volume testing with bulk operations
4. Endurance testing scenarios
5. Resource leak detection tests

Each scenario should be a Locust user class with specific performance goals.
Output: Complete Python file content only."""

        try:
            enhanced_content = await self._call_ai_service(prompt)
            if enhanced_content and self._validate_python_code(enhanced_content):
                return enhanced_content
        except Exception as e:
            logger.warning(f"Performance scenarios generation failed: {e}")

        return None

    def _fix_message_sequence(self, messages: List[Dict]) -> List[Dict]:
        """Ensure proper message sequence for Together AI"""
        if not messages:
            return []

        fixed_messages = []
        last_role = None

        for message in messages:
            role = message['role']

            # Skip system messages in sequence checking
            if role == 'system':
                fixed_messages.append(message)
                continue

            # Avoid consecutive messages from same role
            if role == last_role:
                # If we have consecutive user or assistant messages, merge them
                if fixed_messages and fixed_messages[-1]['role'] == role:
                    # Merge with previous message
                    fixed_messages[-1]['content'] += '\n\n' + message['content']
                else:
                    fixed_messages.append(message)
            else:
                fixed_messages.append(message)

            last_role = role

        return fixed_messages

    def _validate_and_clean_messages(self, messages: List[Dict]) -> List[Dict]:
        """Validate and clean message format for Together AI"""
        if not messages:
            return []

        validated_messages = []

        for i, message in enumerate(messages):
            try:
                # Ensure message is a dictionary
                if not isinstance(message, dict):
                    logger.warning(f"Message {i} is not a dict, skipping: {type(message)}")
                    continue

                # Ensure required fields exist
                if 'role' not in message or 'content' not in message:
                    logger.warning(f"Message {i} missing role or content, skipping: {message}")
                    continue

                # Validate role
                role = message.get('role')
                if role not in ['system', 'user', 'assistant']:
                    logger.warning(f"Message {i} has invalid role '{role}', skipping")
                    continue

                # Validate and clean content
                content = message.get('content')
                if content is None:
                    logger.warning(f"Message {i} has None content, skipping")
                    continue

                # Convert content to string and clean
                content = str(content).strip()
                if not content:
                    logger.warning(f"Message {i} has empty content after cleaning, skipping")
                    continue

                # Create clean message
                clean_message = {
                    "role": role,
                    "content": content
                }

                validated_messages.append(clean_message)

            except Exception as e:
                logger.error(f"Error processing message {i}: {e}")
                continue

        # Ensure alternating user/assistant pattern (except for system)
        final_messages = self._fix_message_sequence(validated_messages)

        return final_messages

    async def _call_ai_service(self, prompt: str, old_messages: List[Dict] = None) -> Optional[str]:
        """Call AI service with retry logic and validation"""
        if old_messages is None:
            old_messages = []
        validated_old_messages = self._validate_and_clean_messages(old_messages)

        messages = [
            {
                "role": "system",
                "content": "You are an expert Python developer specializing in Locust load testing. Generate clean, production-ready code with proper error handling. "
                           "Always return your code wrapped in <code></code> tags with no explanations outside the tags and DO NOT TRUNCATE THE CODE. "
                           "Format: <code>your_python_code_here</code>",
            },
            {"role": "user", "content": prompt},
        ]
        # Add old messages if they exist
        if validated_old_messages:
            messages.extend(validated_old_messages)


        for attempt in range(3):  # Retry logic
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.ai_client.chat.completions.create,
                        model=self.ai_config.model,
                        messages=messages,
                        max_tokens=self.ai_config.max_tokens,
                        temperature=self.ai_config.temperature,
                        top_p=0.9,
                        top_k=40,
                        repetition_penalty=1.1,
                    ),
                    timeout=self.ai_config.timeout,
                )

                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content.strip()


                    # Clean up the response
                    content = self._clean_ai_response(self.extract_code_from_response(content))

                    if content:
                        return content

            except asyncio.TimeoutError:
                logger.warning(f"AI service timeout on attempt {attempt + 1}")

            except Exception as e:
                logger.warning(f"AI service error on attempt {attempt + 1}: {e}")


            if attempt < 2:  # Wait before retry
                await asyncio.sleep(2**attempt)
        print(f"issue for prompt {prompt}")
        return ""

    def extract_code_from_response(self,response_text):
        # Extract content between <code> tags

        code_match = re.search(r'<code>(.*?)</code>', response_text, re.DOTALL)
        if code_match:
            content = code_match.group(1).strip()
            # Additional validation - ensure we got actual content
            if content and len(content) > 0:
                return content


        return response_text.strip()


    def _clean_ai_response(self, content: str) -> str:
        """Clean and validate AI response"""
        # Remove markdown code blocks if present
        if content.startswith("```python") and content.endswith("```"):
            content = content[9:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()

        # Remove any explanatory text before/after code
        lines = content.split("\n")
        start_idx = 0
        end_idx = len(lines)

        # Find actual Python code start
        for i, line in enumerate(lines):
            if line.strip().startswith(
                ("import ", "from ", "class ", "def ", '"""', "'''")
            ):
                start_idx = i
                break

        # Find actual Python code end (remove trailing explanations)
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if (
                line
                and not line.startswith("#")
                and not line.lower().startswith(("note:", "this", "the "))
            ):
                end_idx = i + 1
                break

        return "\n".join(lines[start_idx:end_idx])

    def _analyze_api_domain(
        self, endpoints: List[Endpoint], api_info: Dict[str, Any]
    ) -> str:
        """Analyze API to determine domain and patterns"""
        analysis = []

        # API info analysis
        analysis.append(f"API Title: {api_info.get('title', 'Unknown')}")
        analysis.append(f"Description: {api_info.get('description', 'No description')}")

        # Endpoint analysis
        methods = [ep.method for ep in endpoints]
        paths = [ep.path for ep in endpoints]

        analysis.append(f"Total Endpoints: {len(endpoints)}")
        analysis.append(f"HTTP Methods: {', '.join(set(methods))}")
        analysis.append(f"Common Path Patterns: {self._extract_path_patterns(paths)}")

        # Resource analysis
        resources = self._extract_resources_from_paths(paths)
        analysis.append(f"Main Resources: {', '.join(resources[:5])}")

        return "\n".join(analysis)

    def _format_endpoints_for_prompt(self, endpoints: List[Endpoint]) -> str:
        """Format endpoints for AI prompt"""
        formatted = []
        for ep in endpoints:
            params = f"({len(ep.parameters)} params)" if ep.parameters else ""
            body = "(with body)" if ep.request_body else ""
            formatted.append(
                f"- {ep.method} {ep.path} {params} {body} - {ep.summary or 'No summary'}"
            )

        return "\n".join(formatted)

    def _extract_schema_patterns(self, endpoints: List[Endpoint]) -> str:
        """Extract common schema patterns from endpoints"""
        patterns = []

        for ep in endpoints:
            if ep.request_body and ep.request_body.schema:
                schema = ep.request_body.schema
                if schema.get("properties"):
                    fields = list(schema["properties"].keys())
                    patterns.append(f"{ep.path} ({ep.method}): {', '.join(fields[:5])}")

        return "\n".join(patterns[:10])  # Limit for token efficiency

    def _extract_validation_patterns(self, endpoints: List[Endpoint]) -> str:
        """Extract validation patterns needed for endpoints"""
        patterns = []

        for ep in endpoints:
            for response in ep.responses:
                if response.status_code.startswith("2"):  # Success responses
                    pattern = f"{ep.method} {ep.path} -> {response.status_code}"
                    if response.schema:
                        pattern += f" (schema validation needed)"
                    patterns.append(pattern)

        return "\n".join(patterns[:10])

    def _analyze_performance_patterns(self, endpoints: List[Endpoint]) -> str:
        """Analyze endpoints for performance testing patterns"""
        analysis = []

        # Categorize endpoints by performance characteristics
        read_heavy = [ep for ep in endpoints if ep.method == "GET"]
        write_heavy = [ep for ep in endpoints if ep.method in ["POST", "PUT", "PATCH"]]
        bulk_candidates = [
            ep
            for ep in endpoints
            if "bulk" in ep.path.lower() or "batch" in ep.path.lower()
        ]

        analysis.append(
            f"Read-heavy endpoints: {len(read_heavy)} (good for load testing)"
        )
        analysis.append(
            f"Write-heavy endpoints: {len(write_heavy)} (good for stress testing)"
        )
        analysis.append(
            f"Bulk operation endpoints: {len(bulk_candidates)} (good for volume testing)"
        )

        # Identify endpoints that might be resource intensive
        complex_endpoints = [
            ep
            for ep in endpoints
            if ep.request_body
            and ep.request_body.schema
            and len(ep.request_body.schema.get("properties", {})) > 5
        ]
        analysis.append(
            f"Complex endpoints: {len(complex_endpoints)} (monitor for performance)"
        )

        return "\n".join(analysis)

    def _extract_path_patterns(self, paths: List[str]) -> str:
        """Extract common patterns from API paths"""
        patterns = set()
        for path in paths:
            # Extract patterns like /api/v1/{resource}
            parts = path.split("/")
            if len(parts) > 2:
                pattern = "/".join(parts[:3])
                if "{" in pattern:
                    pattern = (
                        pattern.replace("{id}", "{id}")
                        .replace("{", "{")
                        .replace("}", "}")
                    )
                patterns.add(pattern)

        return ", ".join(list(patterns)[:5])

    def _extract_resources_from_paths(self, paths: List[str]) -> List[str]:
        """Extract resource names from API paths"""
        resources = set()
        for path in paths:
            parts = [p for p in path.split("/") if p and not p.startswith("{")]
            for part in parts:
                if len(part) > 2 and part.isalpha():  # Likely a resource name
                    resources.add(part)

        return sorted(list(resources))

    async def _create_test_files_safely(
        self,
        test_files: Dict[str, str],
        output_path: Path,
        max_file_size: int = 1024 * 1024,  # 1MB limit
    ) -> list:
        """
        Create test files safely with comprehensive security and error handling
        """
        created_files = []
        temp_dir = output_path / f"temp_{uuid.uuid4().hex[:8]}"

        # Security validation
        allowed_extensions = {
            ".py",
            ".md",
            ".txt",
            ".sh",
            ".yml",
            ".yaml",
            ".json",
            ".example",
        }

        try:
            # Ensure output directory exists
            output_path.mkdir(parents=True, exist_ok=True)
            temp_dir.mkdir(parents=True, exist_ok=True)

            for filename, content in test_files.items():
                try:
                    # Security checks
                    clean_filename = self._sanitize_filename(filename)

                    file_extension = Path(clean_filename).suffix.lower()


                    if file_extension not in allowed_extensions:
                        logger.warning(
                            f"⚠️ Skipping file with disallowed extension: {filename}"
                        )
                        continue

                    if len(content.encode("utf-8")) > max_file_size:
                        logger.warning(f"⚠️ File too large, truncating: {filename}")
                        content = content[: max_file_size // 2]  # Safe truncation



                    # Create file in temp directory first (atomic operation)
                    temp_file_path = temp_dir / clean_filename
                    await asyncio.to_thread(
                        temp_file_path.write_text, content, encoding="utf-8"
                    )

                    # Set appropriate permissions
                    if clean_filename.endswith(".sh"):
                        temp_file_path.chmod(0o755)  # Executable
                    else:
                        temp_file_path.chmod(0o644)  # Read/write

                    created_files.append(
                        {
                            "filename": clean_filename,
                            "temp_path": temp_file_path,
                            "final_path": output_path / clean_filename,
                            "size": len(content.encode("utf-8")),
                            "type": file_extension.lstrip("."),
                        }
                    )

                    logger.info(f"📄 Prepared: {clean_filename} ({len(content)} chars)")

                except Exception as e:
                    logger.error(f"❌ Failed to prepare file {filename}: {e}")
                    continue

            # Atomic move to final location (all or nothing)
            if created_files:
                for file_info in created_files:
                    try:
                        await asyncio.to_thread(
                            shutil.move,
                            str(file_info["temp_path"]),
                            str(file_info["final_path"]),
                        )
                        file_info["path"] = file_info["final_path"]
                        logger.info(f"✅ Created: {file_info['filename']}")
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to move file {file_info['filename']}: {e}"
                        )
                        # Remove from created_files if move failed
                        created_files = [f for f in created_files if f != file_info]

            return created_files

        except Exception as e:
            logger.error(f"❌ File creation process failed: {e}")
            return []

        finally:
            # Always clean up temp directory
            if temp_dir.exists():
                try:
                    await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to cleanup temp directory: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent security issues"""
        # Remove directory components
        clean_name = os.path.basename(filename).lower()

        # Remove dangerous characters
        clean_name = re.sub(r'[<>:"/\\|?*]', "", clean_name)
        # Replace spaces with underscores
        clean_name = clean_name.replace("- ", "_")

        # Ensure reasonable length
        if len(clean_name) > 255:
            name_part, ext = os.path.splitext(clean_name)
            clean_name = name_part[:250] + ext

        # Prevent hidden files and ensure not empty
        safe_dotfiles = {".env.example", ".gitignore", ".env.template"}
        if not clean_name or (
            clean_name.startswith(".") and clean_name not in safe_dotfiles
        ):
            clean_name = f"generated_{uuid.uuid4().hex[:8]}.py"

        return clean_name

    def _validate_python_code(self, content: str) -> bool:
        """Validate Python code syntax"""
        try:
            compile(content, "<string>", "exec")
            return True
        except SyntaxError:
            return False
