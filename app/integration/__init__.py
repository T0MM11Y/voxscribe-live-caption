"""Optional local integration APIs."""

from app.integration.openapi import VoxScribeOpenApiServer, build_openapi_spec

__all__ = ["VoxScribeOpenApiServer", "build_openapi_spec"]
