"""
Workflow dispatcher for routing between modular and monolithic implementations.

This module provides a unified entry point that checks the MUSIC_WORKFLOW_USE_MODULAR
feature flag and routes execution to the appropriate implementation.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from music_workflow.config.settings import get_settings
from music_workflow.utils.logging import MusicWorkflowLogger

logger = MusicWorkflowLogger("dispatcher")


class WorkflowDispatcher:
    """Routes workflow execution based on feature flags."""

    def __init__(self):
        """Initialize the dispatcher."""
        self.settings = get_settings()
        self._monolithic_module = None

    def should_use_modular(self) -> bool:
        """Check if modular implementation should be used."""
        return self.settings.should_use_modular()

    def _get_monolithic_module(self):
        """Lazy-load the monolithic module."""
        if self._monolithic_module is None:
            # Add monolithic scripts to path
            monolithic_path = Path(__file__).parent.parent / "monolithic-scripts"
            if monolithic_path.exists() and str(monolithic_path) not in sys.path:
                sys.path.insert(0, str(monolithic_path))

            try:
                # Import the monolithic module
                import importlib.util
                import sys
                spec = importlib.util.spec_from_file_location(
                    "soundcloud_download_prod_merge",
                    monolithic_path / "soundcloud_download_prod_merge-2.py"
                )
                if spec and spec.loader:
                    self._monolithic_module = importlib.util.module_from_spec(spec)
                    # Fix Python 3.13 @dataclass compatibility - register module before exec
                    sys.modules[spec.name] = self._monolithic_module
                    spec.loader.exec_module(self._monolithic_module)
            except Exception as e:
                logger.warning(f"Could not load monolithic module: {e}")
                self._monolithic_module = None

        return self._monolithic_module

    def process_url(
        self,
        url: str,
        output_dir: Optional[Path] = None,
        formats: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Process a URL through the appropriate workflow.

        Args:
            url: URL to process (SoundCloud, YouTube, etc.)
            output_dir: Optional output directory
            formats: List of output formats
            **kwargs: Additional options

        Returns:
            Dict with processing results
        """
        if self.should_use_modular():
            return self._process_modular(url, output_dir, formats, **kwargs)
        else:
            return self._process_monolithic(url, output_dir, formats, **kwargs)

    def _process_modular(
        self,
        url: str,
        output_dir: Optional[Path],
        formats: Optional[List[str]],
        **kwargs
    ) -> Dict[str, Any]:
        """Process through modular workflow."""
        logger.info(f"Processing via MODULAR workflow: {url}")

        from music_workflow.core.workflow import MusicWorkflow, WorkflowOptions

        options = WorkflowOptions(
            download_formats=formats or ["m4a"],
            analyze_audio=kwargs.get("analyze", True),
            organize_files=kwargs.get("organize", True),
            dry_run=kwargs.get("dry_run", False),
        )

        workflow = MusicWorkflow(options=options)
        result = workflow.process_url(url, output_dir=output_dir)

        return {
            "success": result.success,
            "track": {
                "id": result.track.id,
                "title": result.track.title,
                "artist": result.track.artist,
                "bpm": result.track.bpm,
                "key": result.track.key,
                "duration": result.track.duration,
            },
            "errors": result.errors,
            "warnings": result.warnings,
            "execution_time": result.execution_time_seconds,
            "workflow": "modular",
        }

    def _process_monolithic(
        self,
        url: str,
        output_dir: Optional[Path],
        formats: Optional[List[str]],
        **kwargs
    ) -> Dict[str, Any]:
        """Process through monolithic script."""
        logger.info(f"Processing via MONOLITHIC workflow: {url}")

        monolithic = self._get_monolithic_module()
        if monolithic is None:
            # Fall back to modular if monolithic unavailable
            logger.warning("Monolithic unavailable, falling back to modular")
            return self._process_modular(url, output_dir, formats, **kwargs)

        try:
            # Call the monolithic workflow function
            # This depends on the monolithic script's interface
            if hasattr(monolithic, 'process_url'):
                result = monolithic.process_url(url)
            elif hasattr(monolithic, 'main'):
                result = monolithic.main(url)
            else:
                logger.warning("Monolithic module missing expected functions")
                return self._process_modular(url, output_dir, formats, **kwargs)

            return {
                "success": True,
                "result": result,
                "workflow": "monolithic",
            }
        except Exception as e:
            logger.error(f"Monolithic workflow failed: {e}")
            return {
                "success": False,
                "errors": [str(e)],
                "workflow": "monolithic",
            }

    def process_batch(
        self,
        urls: List[str],
        output_dir: Optional[Path] = None,
        formats: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Dict[str, Any]]:
        """Process multiple URLs.

        Args:
            urls: List of URLs to process
            output_dir: Optional output directory
            formats: List of output formats
            **kwargs: Additional options

        Returns:
            Dict mapping URLs to their results
        """
        results = {}
        for url in urls:
            results[url] = self.process_url(url, output_dir, formats, **kwargs)
        return results


# Convenience function
def dispatch_workflow(
    url: str,
    output_dir: Optional[Path] = None,
    formats: Optional[List[str]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Dispatch a single URL to the appropriate workflow.

    This is the main entry point for feature-flag-aware workflow execution.

    Args:
        url: URL to process
        output_dir: Optional output directory
        formats: List of output formats
        **kwargs: Additional options

    Returns:
        Dict with processing results
    """
    dispatcher = WorkflowDispatcher()
    return dispatcher.process_url(url, output_dir, formats, **kwargs)


def get_active_workflow() -> str:
    """Get the name of the currently active workflow.

    Returns:
        'modular' or 'monolithic' based on feature flag
    """
    settings = get_settings()
    return "modular" if settings.should_use_modular() else "monolithic"
