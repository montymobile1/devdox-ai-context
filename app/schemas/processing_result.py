from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any


class ProcessingResult(BaseModel):
    # allow non-pydantic, arbitrary Python types (like exceptions)
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    success: bool
    context_id: Optional[str] = None
    error_object: Optional[BaseException] = Field(default=None, exclude=True)
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    chunks_created: Optional[int] = None
    embeddings_created: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
