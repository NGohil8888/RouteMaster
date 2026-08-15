import httpx
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class OllamaClient:
    """HTTP client for communicating with Ollama servers."""
    
    def __init__(self, base_url: str, timeout: int = 120):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Base URL of the Ollama server (e.g., http://localhost:11434)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def get_tags(self) -> Dict[str, Any]:
        """
        Get list of available models from Ollama server.
        
        Returns:
            Dictionary with 'models' key containing list of available models
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get tags from {self.base_url}: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if Ollama server is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for {self.base_url}: {e}")
            return False
    
    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        num_predict: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any] | AsyncGenerator[str, None]:
        """
        Send a chat completion request to Ollama.
        
        Args:
            model: Model name
            messages: List of message dictionaries with 'role' and 'content'
            stream: Whether to stream the response
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            top_k: Top-k sampling parameter
            num_predict: Maximum tokens to predict
            **kwargs: Additional parameters to pass to Ollama
        
        Returns:
            Response dictionary or async generator if streaming
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        
        # Add optional parameters
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if top_k is not None:
            options["top_k"] = top_k
        if num_predict is not None:
            options["num_predict"] = num_predict
        
        if options:
            payload["options"] = options
        
        payload.update(kwargs)
        
        try:
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout if not stream else None
            )
            response.raise_for_status()
            
            if stream:
                return self._stream_response(response)
            else:
                return response.json()
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise
    
    async def _stream_response(self, response: httpx.Response) -> AsyncGenerator[str, None]:
        """Handle streaming response from Ollama."""
        import json
        async for line in response.aiter_lines():
            if line.strip():
                try:
                    chunk = json.loads(line)
                    yield json.dumps(chunk)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse stream line: {line}")
    
    async def generate_embedding(self, model: str, prompt: str) -> Dict[str, Any]:
        """
        Generate embeddings using Ollama.
        
        Args:
            model: Embedding model name
            prompt: Text to embed
        
        Returns:
            Response with embedding vector
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": prompt}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
