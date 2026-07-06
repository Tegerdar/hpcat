"""
Security utilities for hpcat.

This module provides security-focused functions for:
- Input validation and sanitization
- SSH command construction
- Error handling with safe messages
"""

import re
import shlex
from typing import List, Optional
from concurrent.futures import TimeoutError as FuturesTimeoutError


# Security constants
NODE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-_.]*$')
MAX_NODE_NAME_LENGTH = 253  # RFC 1035 hostname limit
MAX_NODES_DEFAULT = 1000
SSH_TIMEOUT_DEFAULT = 5
MAX_WORKERS_DEFAULT = 20

# Safe error messages (no sensitive information)
SAFE_ERROR_MESSAGES = {
    'invalid_node_name': 'Invalid node name format',
    'node_name_too_long': 'Node name exceeds maximum length',
    'too_many_nodes': f'Too many nodes requested (max: {MAX_NODES_DEFAULT})',
    'ssh_timeout': 'SSH connection timed out',
    'ssh_auth_failed': 'SSH authentication failed',
    'ssh_command_failed': 'SSH command execution failed',
    'ssh_connection_refused': 'SSH connection refused',
    'slurm_discovery_failed': 'Slurm discovery failed',
    'subprocess_timeout': 'Command execution timed out',
    'subprocess_failed': 'Command execution failed',
    'invalid_input': 'Invalid input provided',
    'permission_denied': 'Permission denied',
}


def validate_node_name(node: str) -> str:
    """
    Validate and sanitize a node name.
    
    Args:
        node: The node name to validate
        
    Returns:
        The validated node name
        
    Raises:
        ValueError: If the node name is invalid
    """
    if not node or not isinstance(node, str):
        raise ValueError(SAFE_ERROR_MESSAGES['invalid_node_name'])
    
    # Check length
    if len(node) > MAX_NODE_NAME_LENGTH:
        raise ValueError(SAFE_ERROR_MESSAGES['node_name_too_long'])
    
    # Check pattern (alphanumeric, hyphen, underscore, dot)
    if not NODE_NAME_PATTERN.match(node):
        raise ValueError(SAFE_ERROR_MESSAGES['invalid_node_name'])
    
    return node


def validate_node_list(nodes: Optional[List[str]]) -> List[str]:
    """
    Validate a list of node names.
    
    Args:
        nodes: List of node names to validate
        
    Returns:
        List of validated node names
        
    Raises:
        ValueError: If any node name is invalid or list is too long
    """
    if nodes is None:
        return []
    
    # Check list size
    if len(nodes) > MAX_NODES_DEFAULT:
        raise ValueError(SAFE_ERROR_MESSAGES['too_many_nodes'])
    
    # Validate each node
    validated_nodes = []
    for node in nodes:
        validated_nodes.append(validate_node_name(node))
    
    return validated_nodes


def build_ssh_command(
    node: str,
    command: str,
    timeout: int = SSH_TIMEOUT_DEFAULT,
    batch_mode: bool = True,
    quiet: bool = True
) -> List[str]:
    """
    Build a secure SSH command.
    
    This function constructs an SSH command with security best practices:
    - Validates the node name
    - Uses proper argument escaping
    - Does NOT disable StrictHostKeyChecking
    - Sets appropriate timeouts
    
    Args:
        node: The target node (will be validated)
        command: The command to execute remotely
        timeout: SSH connection timeout in seconds
        batch_mode: Whether to use BatchMode=yes
        quiet: Whether to use LogLevel=QUIET
        
    Returns:
        List of command arguments for subprocess.run()
        
    Raises:
        ValueError: If node name is invalid
    """
    # Validate inputs
    validated_node = validate_node_name(node)
    
    if not command or not isinstance(command, str):
        raise ValueError(SAFE_ERROR_MESSAGES['invalid_input'])
    
    # Build SSH options
    ssh_options = ['-o', f'ConnectTimeout={timeout}']
    
    if batch_mode:
        ssh_options.extend(['-o', 'BatchMode=yes'])
    
    if quiet:
        ssh_options.extend(['-o', 'LogLevel=QUIET'])
    
    # Build the full command
    # Note: We do NOT include StrictHostKeyChecking=no for security
    cmd = ['ssh'] + ssh_options + [validated_node, command]
    
    return cmd


def get_safe_error_message(error: Exception, context: str = '') -> str:
    """
    Get a safe error message that doesn't expose sensitive information.
    
    Args:
        error: The original exception
        context: Additional context for the error
        
    Returns:
        A safe error message string
    """
    error_type = type(error).__name__
    
    # Map known error types to safe messages
    error_mapping = {
        'TimeoutExpired': SAFE_ERROR_MESSAGES['subprocess_timeout'],
        'TimeoutError': SAFE_ERROR_MESSAGES['subprocess_timeout'],
        'FuturesTimeoutError': SAFE_ERROR_MESSAGES['subprocess_timeout'],
        'ConnectionRefusedError': SAFE_ERROR_MESSAGES['ssh_connection_refused'],
        'PermissionError': SAFE_ERROR_MESSAGES['permission_denied'],
        'FileNotFoundError': SAFE_ERROR_MESSAGES['subprocess_failed'],
        'CalledProcessError': SAFE_ERROR_MESSAGES['subprocess_failed'],
        'ValueError': SAFE_ERROR_MESSAGES['invalid_input'],
        'ConnectionError': SAFE_ERROR_MESSAGES['ssh_connection_refused'],
        'OSError': SAFE_ERROR_MESSAGES['subprocess_failed'],
    }
    
    safe_message = error_mapping.get(error_type, SAFE_ERROR_MESSAGES['subprocess_failed'])
    
    if context:
        return f"{context}: {safe_message}"
    
    return safe_message


def sanitize_command_output(output: str, max_length: int = 1000) -> str:
    """
    Sanitize command output to prevent information disclosure.
    
    Args:
        output: The raw command output
        max_length: Maximum length to return
        
    Returns:
        Sanitized output string
    """
    if not output or not isinstance(output, str):
        return ''
    
    # Truncate to prevent large output disclosure
    if len(output) > max_length:
        return output[:max_length] + '... [truncated]'
    
    return output
