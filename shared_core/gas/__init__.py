"""
Google Apps Script (GAS) Integration Module
===========================================

Provides unified interface for GAS deployment and execution.

Usage:
    from shared_core.gas import GASDeployment, deploy_project, update_project

    # Using the class
    deployer = GASDeployment()
    result = deployer.deploy("/path/to/project", "My Project")

    # Using convenience functions
    result = deploy_project("/path/to/project", "My Project")
    result = update_project("SCRIPT_ID", "/path/to/project")

The module uses Google Apps Script API as the primary deployment method,
with clasp CLI as an automatic fallback when API operations fail.
"""

from .gas_deployment import (
    GASDeployment,
    DeploymentResult,
    DeploymentMethod,
    deploy_project,
    update_project,
    execute_function,
)

__all__ = [
    'GASDeployment',
    'DeploymentResult',
    'DeploymentMethod',
    'deploy_project',
    'update_project',
    'execute_function',
]
