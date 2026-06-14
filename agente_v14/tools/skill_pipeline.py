"""
=============================================================
AGENTE v14 - SkillPipeline
=============================================================
Pipeline for chaining skill results.
Manages data flow between skills, eliminating the need for the LLM
to manually transcribe intermediate results.

Usage:
    pipeline = SkillPipeline()

    # Agent searches web
    result1 = buscar_web("precio bitcoin")
    pipeline.store("search_result", result1, "text", tool_name="buscar_web")

    # Agent creates chart using previous result
    chart_result = crear_grafico(datos=pipeline.get("search_result"))
    pipeline.store("chart_path", chart_result, "file_path", tool_name="crear_grafico")

    # Agent creates PDF using both artifacts
    pdf_result = crear_pdf(contenido=pipeline.get("search_result"))
=============================================================
"""

from __future__ import annotations

import re
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class SkillPipeline:
    """
    Manages data flow between chained skills.
    
    Usage:
        pipeline = SkillPipeline()
        
        # Agent searches web
        result1 = buscar_web("precio bitcoin")
        pipeline.store("search_result", result1, "text", tool_name="buscar_web")
        
        # Agent creates chart using previous result
        chart_result = crear_grafico(datos=pipeline.get("search_result"))
        pipeline.store("chart_path", chart_result, "file_path", tool_name="crear_grafico")
        
        # Agent creates PDF using both artifacts
        pdf_result = crear_pdf(contenido=pipeline.get("search_result"))
    """
    
    def __init__(self):
        self._artifacts: dict[str, dict] = {}
        self._execution_log: list[dict] = []
        self._created_at = datetime.now().isoformat()
    
    def store(self, key: str, value: Any, artifact_type: str,
              tool_name: str = "", metadata: dict = None):
        """
        Store a pipeline artifact.
        
        Args:
            key: Unique identifier (e.g., "search_results", "chart_path")
            value: The artifact value
            artifact_type: "text", "file_path", "data_json", "image_path", "url"
            tool_name: Tool that generated this artifact
            metadata: Additional info
        """
        self._artifacts[key] = {
            "value": value,
            "type": artifact_type,
            "tool": tool_name,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }
        self._execution_log.append({
            "action": "store",
            "key": key,
            "type": artifact_type,
            "tool": tool_name,
        })
    
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve an artifact by key."""
        artifact = self._artifacts.get(key)
        return artifact["value"] if artifact else default
    
    def resolve_params(self, params: dict) -> dict:
        """
        Resolve artifact references in parameters.
        
        Syntax: "{artifact:KEY}" or "{pipeline:KEY}"
        
        Example:
            params = {"datos": "{artifact:search_results}"}
            → params = {"datos": "Bitcoin está en $98,000..."}
        """
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str):
                def replace_ref(match):
                    artifact_key = match.group(1)
                    artifact_val = self.get(artifact_key)
                    if artifact_val is not None:
                        if isinstance(artifact_val, str):
                            return artifact_val[:2000]
                        return json.dumps(artifact_val)[:2000]
                    return match.group(0)
                
                v = re.sub(r'\{(?:artifact|pipeline):([^}]+)\}', replace_ref, v)
            resolved[k] = v
        return resolved
    
    def auto_store_from_result(self, tool_name: str, result: str) -> str | None:
        """
        Auto-detect what type of artifact a tool produced and store it.
        Returns the artifact key, or None if nothing to store.
        """
        # Detect file paths in result
        file_patterns = [
            (r'guardado.*?en\s+([^\s]+\.[a-z]{2,4})', "file_path"),
            (r'creado\s+([^\s]+\.[a-z]{2,4})', "file_path"),
            (r'ruta[:\s]+([^\s]+\.[a-z]{2,4})', "file_path"),
            (r'archivo[:\s]+([^\s]+\.[a-z]{2,4})', "file_path"),
        ]
        
        for pattern, artifact_type in file_patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                file_path = match.group(1)
                key = f"{tool_name}_output"
                self.store(key, file_path, artifact_type, tool_name=tool_name)
                return key
        
        # If no file path, store as text if substantial
        if len(result) > 50 and "ERROR" not in result:
            key = f"{tool_name}_result"
            self.store(key, result, "text", tool_name=tool_name)
            return key
        
        return None
    
    def get_context_summary(self, max_chars: int = 500) -> str:
        """
        Generate summary of available artifacts for LLM context.
        """
        if not self._artifacts:
            return ""
        
        lines = ["ARTIFACTS DISPONIBLES EN EL PIPELINE:"]
        for key, data in self._artifacts.items():
            value_preview = str(data["value"])[:100]
            lines.append(
                f"  {key} ({data['type']}, de {data['tool']}): "
                f"{value_preview}{'...' if len(str(data['value'])) > 100 else ''}"
            )
        lines.append("Usa '{artifact:NOMBRE}' en parámetros para referenciar estos datos.")
        return "\n".join(lines)[:max_chars]
    
    def reset(self):
        """Clear the pipeline (new task)."""
        self._artifacts.clear()
        self._execution_log.clear()
    
    def to_dict(self) -> dict:
        """Serialize for debugging/logging."""
        return {
            "artifacts": {
                k: {
                    "type": v["type"],
                    "tool": v["tool"],
                    "value_preview": str(v["value"])[:200],
                }
                for k, v in self._artifacts.items()
            },
            "execution_log": self._execution_log,
            "created_at": self._created_at,
        }
