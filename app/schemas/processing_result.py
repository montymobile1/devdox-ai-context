from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import Optional, Dict, Any
from typing import Literal
import re


class ProcessingResult(BaseModel):
    success: bool
    context_id: Optional[str] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    chunks_created: Optional[int] = None
    embeddings_created: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SwaggerProcessingRequest(BaseModel):
    context_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-_]+$')
    repo_id: str = Field(..., pattern=r'^[0-9]+$')
    user_id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')

    git_provider: Literal["github", "gitlab"]
    swagger_source: Literal["url", "file"]
    swagger_url: Optional[str] = None
    swagger_file_path: Optional[str] = None
    git_config: Dict[str, Any] = None

    @field_validator('swagger_url')
    @classmethod
    def validate_url_when_source_is_url(cls, v, info: ValidationInfo):
        # Access other field values through info.data
        if info.data.get('swagger_source') == 'url' and not v:
            raise ValueError('swagger_url is required when source is url')
        return v

    @field_validator('swagger_file_path')
    @classmethod
    def validate_path_when_source_is_file(cls, v, info: ValidationInfo):
        if info.data.get('swagger_source') == 'file' and not v:
            raise ValueError('swagger_file_path is required when source is file')
        return v