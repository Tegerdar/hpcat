"""
Security tests for hpcat.

This module contains comprehensive security tests for:
- Input validation and sanitization
- SSH command construction
- Error handling
- Command injection prevention
"""

import unittest
import re
from unittest.mock import patch, MagicMock
import subprocess

from hpcat.security import (
    validate_node_name,
    validate_node_list,
    build_ssh_command,
    get_safe_error_message,
    NODE_NAME_PATTERN,
    MAX_NODE_NAME_LENGTH,
    MAX_NODES_DEFAULT,
    SAFE_ERROR_MESSAGES,
)


class TestNodeNameValidation(unittest.TestCase):
    """Test node name validation functionality."""
    
    def test_valid_node_names(self):
        """Test that valid node names are accepted."""
        valid_names = [
            'node01',
            'compute-01',
            'gpu_node_01',
            'node123',
            'a',  # Single character
            'node-123-abc',
            'node_123_abc',
            'node.123',
            'Node01',  # Mixed case
            'node-123-abc-def',
        ]
        
        for name in valid_names:
            with self.subTest(node_name=name):
                result = validate_node_name(name)
                self.assertEqual(result, name)
    
    def test_invalid_node_names_format(self):
        """Test that invalid node name formats are rejected."""
        invalid_names = [
            '',  # Empty
            ' node01',  # Leading space
            'node01 ',  # Trailing space
            'node 01',  # Space in middle
            'node;rm -rf /',  # Command injection attempt
            'node|cat /etc/passwd',  # Pipe injection
            'node&&echo hacked',  # Command chaining
            'node$(whoami)',  # Command substitution
            'node`whoami`',  # Backtick command substitution
            'node\nmalicious',  # Newline injection
            'node\x00malicious',  # Null byte injection
            'node\tmalicious',  # Tab injection
            'node\rmalicious',  # Carriage return
            '-node01',  # Leading hyphen
            '_node01',  # Leading underscore
            '.node01',  # Leading dot
            'node!@#$%',  # Special characters
            'node<>',  # Angle brackets
            'node{}',  # Curly braces
            'node[]',  # Square brackets
            'node()',  # Parentheses
            'node*',  # Asterisk
            'node?',  # Question mark
            'node~',  # Tilde
            'node`',  # Backtick
            'node\\',  # Backslash
            'node/',  # Forward slash
            'node:',  # Colon
        ]
        
        for name in invalid_names:
            with self.subTest(node_name=repr(name)):
                with self.assertRaises(ValueError) as context:
                    validate_node_name(name)
                self.assertIn('Invalid node name format', str(context.exception))
    
    def test_node_name_length_limit(self):
        """Test that node names exceeding maximum length are rejected."""
        # Create a node name that's too long
        long_name = 'a' * (MAX_NODE_NAME_LENGTH + 1)
        
        with self.assertRaises(ValueError) as context:
            validate_node_name(long_name)
        self.assertIn('exceeds maximum length', str(context.exception))
    
    def test_node_name_max_length_accepted(self):
        """Test that node names at maximum length are accepted."""
        max_name = 'a' * MAX_NODE_NAME_LENGTH
        result = validate_node_name(max_name)
        self.assertEqual(result, max_name)
    
    def test_non_string_node_name(self):
        """Test that non-string node names are rejected."""
        invalid_inputs = [None, 123, [], {}, True, 12.34]
        
        for invalid_input in invalid_inputs:
            with self.subTest(input_type=type(invalid_input)):
                with self.assertRaises(ValueError) as context:
                    validate_node_name(invalid_input)
                self.assertIn('Invalid node name format', str(context.exception))


class TestNodeListValidation(unittest.TestCase):
    """Test node list validation functionality."""
    
    def test_valid_node_list(self):
        """Test that valid node lists are accepted."""
        nodes = ['node01', 'node02', 'compute-01']
        result = validate_node_list(nodes)
        self.assertEqual(result, nodes)
    
    def test_empty_node_list(self):
        """Test that empty node lists are accepted."""
        result = validate_node_list([])
        self.assertEqual(result, [])
    
    def test_none_node_list(self):
        """Test that None node list returns empty list."""
        result = validate_node_list(None)
        self.assertEqual(result, [])
    
    def test_too_many_nodes(self):
        """Test that node lists exceeding maximum are rejected."""
        # Create a list with one more than the maximum
        nodes = [f'node{i:04d}' for i in range(MAX_NODES_DEFAULT + 1)]
        
        with self.assertRaises(ValueError) as context:
            validate_node_list(nodes)
        self.assertIn('Too many nodes requested', str(context.exception))
    
    def test_node_list_with_invalid_names(self):
        """Test that node lists with invalid names are rejected."""
        nodes = ['node01', 'invalid;rm -rf /', 'node02']
        
        with self.assertRaises(ValueError):
            validate_node_list(nodes)
    
    def test_max_nodes_accepted(self):
        """Test that node lists at maximum size are accepted."""
        nodes = [f'node{i:04d}' for i in range(MAX_NODES_DEFAULT)]
        result = validate_node_list(nodes)
        self.assertEqual(len(result), MAX_NODES_DEFAULT)


class TestSSHCommandConstruction(unittest.TestCase):
    """Test SSH command construction security."""
    
    def test_build_ssh_command_basic(self):
        """Test basic SSH command construction."""
        cmd = build_ssh_command('node01', 'echo hello')
        
        # Check that ssh is the first command
        self.assertEqual(cmd[0], 'ssh')
        
        # Check that node is in the command
        self.assertIn('node01', cmd)
        
        # Check that command is in the command
        self.assertIn('echo hello', cmd)
        
        # Check that StrictHostKeyChecking=no is NOT present
        self.assertNotIn('StrictHostKeyChecking=no', cmd)
        
        # Check that ConnectTimeout is present
        timeout_found = any('ConnectTimeout=' in arg for arg in cmd)
        self.assertTrue(timeout_found)
    
    def test_build_ssh_command_with_options(self):
        """Test SSH command construction with various options."""
        cmd = build_ssh_command(
            'node01',
            'lscpu -J',
            timeout=10,
            batch_mode=True,
            quiet=True
        )
        
        # Check BatchMode=yes is present
        self.assertIn('BatchMode=yes', cmd)
        
        # Check LogLevel=QUIET is present
        self.assertIn('LogLevel=QUIET', cmd)
        
        # Check ConnectTimeout=10 is present
        self.assertIn('ConnectTimeout=10', cmd)
    
    def test_build_ssh_command_invalid_node(self):
        """Test that invalid node names raise ValueError."""
        with self.assertRaises(ValueError):
            build_ssh_command('invalid;rm -rf /', 'echo hello')
    
    def test_build_ssh_command_invalid_command(self):
        """Test that invalid commands raise ValueError."""
        with self.assertRaises(ValueError):
            build_ssh_command('node01', '')
        
        with self.assertRaises(ValueError):
            build_ssh_command('node01', None)
    
    def test_build_ssh_command_node_sanitization(self):
        """Test that node names are properly sanitized in commands."""
        # Test with a node name that might cause issues
        cmd = build_ssh_command('node-123', 'echo hello')
        
        # The node name should appear as a single argument
        node_index = cmd.index('node-123')
        
        # Make sure it's not part of a larger string that could be malicious
        self.assertEqual(cmd[node_index], 'node-123')
    
    def test_command_injection_prevention(self):
        """Test that command injection is prevented."""
        # Try to inject commands through node name
        malicious_node = 'node01; echo hacked'
        
        with self.assertRaises(ValueError):
            build_ssh_command(malicious_node, 'echo hello')
        
        # Try to inject commands through command
        # This should work because the command is passed as a single string
        # The shell on the remote side will interpret it, but that's expected
        cmd = build_ssh_command('node01', 'echo hello; echo hacked')
        self.assertIn('echo hello; echo hacked', cmd)
        
        # The important thing is that the node name is validated
        # and the command is passed as a single argument to ssh


class TestErrorHandling(unittest.TestCase):
    """Test error handling and safe error messages."""
    
    def test_safe_error_messages_exist(self):
        """Test that all expected safe error messages exist."""
        expected_messages = [
            'invalid_node_name',
            'node_name_too_long',
            'too_many_nodes',
            'ssh_timeout',
            'ssh_auth_failed',
            'ssh_command_failed',
            'ssh_connection_refused',
            'slurm_discovery_failed',
            'subprocess_timeout',
            'subprocess_failed',
            'invalid_input',
            'permission_denied',
        ]
        
        for msg_key in expected_messages:
            with self.subTest(message_key=msg_key):
                self.assertIn(msg_key, SAFE_ERROR_MESSAGES)
    
    def test_get_safe_error_message_known_errors(self):
        """Test safe error messages for known error types."""
        # Test TimeoutError
        try:
            raise TimeoutError("test timeout")
        except TimeoutError as e:
            safe_msg = get_safe_error_message(e, 'Test')
            self.assertIn('timed out', safe_msg.lower())
        
        # Test ConnectionRefusedError
        try:
            raise ConnectionRefusedError("test connection refused")
        except ConnectionRefusedError as e:
            safe_msg = get_safe_error_message(e, 'Test')
            self.assertIn('refused', safe_msg.lower())
        
        # Test PermissionError
        try:
            raise PermissionError("test permission")
        except PermissionError as e:
            safe_msg = get_safe_error_message(e, 'Test')
            self.assertIn('denied', safe_msg.lower())
    
    def test_get_safe_error_message_unknown_error(self):
        """Test safe error messages for unknown error types."""
        class CustomError(Exception):
            pass
        
        try:
            raise CustomError("sensitive information here")
        except CustomError as e:
            safe_msg = get_safe_error_message(e, 'Test')
            # Should not contain the sensitive information
            self.assertNotIn('sensitive information', safe_msg)
            self.assertIn('failed', safe_msg.lower())
    
    def test_get_safe_error_message_with_context(self):
        """Test safe error messages with context."""
        try:
            raise ValueError("test error")
        except ValueError as e:
            safe_msg = get_safe_error_message(e, 'SSH connection')
            self.assertIn('SSH connection', safe_msg)
            self.assertIn('Invalid input', safe_msg)


class TestRegexPatterns(unittest.TestCase):
    """Test the regex patterns used for validation."""
    
    def test_node_name_pattern(self):
        """Test the node name pattern."""
        # Should match valid node names
        valid_matches = [
            'node01',
            'compute-01',
            'gpu_node_01',
            'node123',
            'a',
            'node-123-abc',
            'node_123_abc',
            'node.123',
            'Node01',
        ]
        
        for name in valid_matches:
            with self.subTest(node_name=name):
                self.assertIsNotNone(NODE_NAME_PATTERN.match(name))
        
        # Should not match invalid node names
        invalid_matches = [
            '',
            ' node01',
            'node01 ',
            'node 01',
            'node;rm',
            'node|cat',
            'node&&echo',
            '-node01',
            '_node01',
            '.node01',
        ]
        
        for name in invalid_matches:
            with self.subTest(node_name=repr(name)):
                self.assertIsNone(NODE_NAME_PATTERN.match(name))


class TestCommandInjectionScenarios(unittest.TestCase):
    """Test specific command injection scenarios."""
    
    def test_ssh_command_injection_via_node_name(self):
        """Test that SSH command injection via node name is prevented."""
        injection_attempts = [
            'node01; echo hacked',
            'node01|cat /etc/passwd',
            'node01&&echo hacked',
            'node01$(whoami)',
            'node01`whoami`',
            'node01\nmalicious',
            'node01\x00malicious',
            'node01\rmalicious',
            'node01\tmalicious',
        ]
        
        for attempt in injection_attempts:
            with self.subTest(attempt=repr(attempt)):
                with self.assertRaises(ValueError):
                    build_ssh_command(attempt, 'echo hello')
    
    def test_ssh_command_injection_via_command(self):
        """Test handling of command injection via command parameter."""
        # The command parameter is passed as a single string to SSH
        # This is expected behavior - the remote shell will interpret it
        # The important thing is that we're not doing shell=True locally
        
        # This should work (command is passed as single argument)
        cmd = build_ssh_command('node01', 'echo hello; echo world')
        self.assertIn('echo hello; echo world', cmd)
        
        # The command should be a single element in the command list
        # (not split by spaces)
        command_part = 'echo hello; echo world'
        self.assertIn(command_part, cmd)


class TestSecurityConstants(unittest.TestCase):
    """Test security-related constants."""
    
    def test_max_node_name_length(self):
        """Test that MAX_NODE_NAME_LENGTH is reasonable."""
        # Should be at least 64 (common hostname limit)
        self.assertGreaterEqual(MAX_NODE_NAME_LENGTH, 64)
        # Should be at most 255 (RFC 1035 limit)
        self.assertLessEqual(MAX_NODE_NAME_LENGTH, 255)
    
    def test_max_nodes_default(self):
        """Test that MAX_NODES_DEFAULT is reasonable."""
        # Should be at least 10
        self.assertGreaterEqual(MAX_NODES_DEFAULT, 10)
        # Should be at most 10000 (reasonable upper limit)
        self.assertLessEqual(MAX_NODES_DEFAULT, 10000)


if __name__ == '__main__':
    unittest.main()
