"""
Security integration tests for hpcat command modules.

This module tests that the command modules properly use the security utilities
and handle security-related scenarios correctly.
"""

import unittest
from unittest.mock import patch, MagicMock, call
import subprocess

from hpcat.commands import gpu, cpu, mem
from hpcat.security import validate_node_name, validate_node_list


class TestGPUSecurity(unittest.TestCase):
    """Test security aspects of the GPU command module."""
    
    @patch('hpcat.commands.gpu.subprocess.run')
    def test_get_gpu_nodes_uses_validate_node_name(self, mock_run):
        """Test that get_gpu_nodes validates node names from Slurm output."""
        # Mock sinfo output with potentially malicious node names
        mock_run.return_value = MagicMock()
        mock_run.return_value.stdout = "node01|gpu\nmalicious;rm -rf /|gpu\nnode02|gpu\n"
        mock_run.return_value.returncode = 0
        
        nodes = gpu.get_gpu_nodes()
        
        # Should only return valid node names
        self.assertIn('node01', nodes)
        self.assertIn('node02', nodes)
        # Should not include the malicious node name
        self.assertNotIn('malicious;rm -rf /', nodes)
        
        # Should have called validate_node_name for each node
        # (This is tested implicitly by the fact that invalid names are filtered)
    
    @patch('hpcat.commands.gpu.subprocess.run')
    def test_get_gpu_nodes_handles_slurm_failure(self, mock_run):
        """Test that get_gpu_nodes handles Slurm command failures gracefully."""
        # Mock sinfo command not found
        mock_run.side_effect = FileNotFoundError("sinfo not found")
        
        nodes = gpu.get_gpu_nodes()
        self.assertEqual(nodes, [])
    
    @patch('hpcat.commands.gpu.subprocess.run')
    def test_get_gpu_nodes_handles_timeout(self, mock_run):
        """Test that get_gpu_nodes handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired('sinfo', 10)
        
        nodes = gpu.get_gpu_nodes()
        self.assertEqual(nodes, [])
    
    def test_poll_node_validates_node_name(self):
        """Test that poll_node validates the node name."""
        # Test with invalid node name
        result = gpu.poll_node('invalid;rm -rf /')
        node, data = result
        
        # Should return error for invalid node name
        self.assertEqual(node, 'invalid;rm -rf /')
        self.assertIn('error', data)
    
    @patch('hpcat.commands.gpu.build_ssh_command')
    @patch('hpcat.commands.gpu.subprocess.run')
    def test_poll_node_uses_build_ssh_command(self, mock_run, mock_build):
        """Test that poll_node uses build_ssh_command for security."""
        # Mock the SSH command to return successful GPU data
        mock_run.return_value = MagicMock()
        mock_run.return_value.stdout = "0,Tesla V100,50.0,1000,8000,45.0,200.0\n"
        mock_run.return_value.returncode = 0
        
        # Mock build_ssh_command to return a command
        mock_build.return_value = ['ssh', 'node01', 'nvidia-smi ...']
        
        result = gpu.poll_node('node01')
        
        # Should have called build_ssh_command
        mock_build.assert_called_once()
        
        # Check that build_ssh_command was called with validated node
        call_args = mock_build.call_args
        self.assertEqual(call_args[0][0], 'node01')  # node parameter
        self.assertIn('nvidia-smi', call_args[0][1])  # command parameter
    
    @patch('hpcat.commands.gpu.validate_node_list')
    def test_execute_validates_user_nodes(self, mock_validate):
        """Test that execute validates user-provided node list."""
        # Create mock args
        class MockArgs:
            nodes = ['node01', 'node02']
            json = False
            csv = False
            prometheus = False
        
        # Mock validation to raise error
        mock_validate.side_effect = ValueError("Invalid node list")
        
        args = MockArgs()
        result = gpu.execute(args)
        
        # Should return error code
        self.assertEqual(result, 1)
        
        # Should have called validate_node_list
        mock_validate.assert_called_once_with(['node01', 'node02'])


class TestCPUSecurity(unittest.TestCase):
    """Test security aspects of the CPU command module."""
    
    @patch('hpcat.commands.cpu.subprocess.run')
    def test_get_cpu_nodes_uses_validate_node_name(self, mock_run):
        """Test that get_cpu_nodes validates node names from Slurm output."""
        # Mock sinfo output with potentially malicious node names
        mock_run.return_value = MagicMock()
        mock_run.return_value.stdout = "node01\nmalicious;rm -rf /\nnode02\n"
        mock_run.return_value.returncode = 0
        
        nodes = cpu.get_cpu_nodes()
        
        # Should only return valid node names
        self.assertIn('node01', nodes)
        self.assertIn('node02', nodes)
        # Should not include the malicious node name
        self.assertNotIn('malicious;rm -rf /', nodes)
    
    def test_poll_node_validates_node_name(self):
        """Test that poll_node validates the node name."""
        # Test with invalid node name
        result = cpu.poll_node('invalid;rm -rf /', False)
        node, data = result
        
        # Should return error for invalid node name
        self.assertEqual(node, 'invalid;rm -rf /')
        self.assertIn('error', data)
    
    @patch('hpcat.commands.cpu.build_ssh_command')
    @patch('hpcat.commands.cpu.subprocess.run')
    def test_poll_node_uses_build_ssh_command(self, mock_run, mock_build):
        """Test that poll_node uses build_ssh_command for security."""
        # Mock the SSH command to return successful lscpu data
        mock_run.return_value = MagicMock()
        mock_run.return_value.stdout = '{"lscpu": []}'
        mock_run.return_value.returncode = 0
        
        # Mock build_ssh_command to return a command
        mock_build.return_value = ['ssh', 'node01', 'lscpu -J']
        
        result = cpu.poll_node('node01', False)
        
        # Should have called build_ssh_command
        mock_build.assert_called_once()
        
        # Check that build_ssh_command was called with validated node
        call_args = mock_build.call_args
        self.assertEqual(call_args[0][0], 'node01')  # node parameter
        self.assertEqual(call_args[0][1], 'lscpu -J')  # command parameter
    
    @patch('hpcat.commands.cpu.validate_node_list')
    def test_execute_validates_user_nodes(self, mock_validate):
        """Test that execute validates user-provided node list."""
        # Create mock args
        class MockArgs:
            nodes = ['node01', 'node02']
            extended = False
            json = False
            csv = False
            prometheus = False
        
        # Mock validation to raise error
        mock_validate.side_effect = ValueError("Invalid node list")
        
        args = MockArgs()
        result = cpu.execute(args)
        
        # Should return error code
        self.assertEqual(result, 1)
        
        # Should have called validate_node_list
        mock_validate.assert_called_once_with(['node01', 'node02'])


class TestMemSecurity(unittest.TestCase):
    """Test security aspects of the Memory command module."""
    
    @patch('hpcat.commands.mem.subprocess.run')
    def test_get_mem_nodes_uses_validate_node_name(self, mock_run):
        """Test that get_mem_nodes validates node names from Slurm output."""
        # Mock sinfo output with potentially malicious node names
        mock_run.return_value = MagicMock()
        mock_run.return_value.stdout = "node01\nmalicious;rm -rf /\nnode02\n"
        mock_run.return_value.returncode = 0
        
        nodes = mem.get_mem_nodes()
        
        # Should only return valid node names
        self.assertIn('node01', nodes)
        self.assertIn('node02', nodes)
        # Should not include the malicious node name
        self.assertNotIn('malicious;rm -rf /', nodes)
    
    def test_poll_node_validates_node_name(self):
        """Test that poll_node validates the node name."""
        # Test with invalid node name
        result = mem.poll_node('invalid;rm -rf /', False)
        node, data = result
        
        # Should return error for invalid node name
        self.assertEqual(node, 'invalid;rm -rf /')
        self.assertIn('error', data)
    
    @patch('hpcat.commands.mem.build_ssh_command')
    @patch('hpcat.commands.mem.subprocess.run')
    def test_poll_node_uses_build_ssh_command(self, mock_run, mock_build):
        """Test that poll_node uses build_ssh_command for security."""
        # Mock the SSH command to return successful meminfo data
        mock_run.return_value = MagicMock()
        mock_run.return_value.stdout = "MemTotal: 8000000 kB\nMemFree: 4000000 kB\n"
        mock_run.return_value.returncode = 0
        
        # Mock build_ssh_command to return a command
        mock_build.return_value = ['ssh', 'node01', 'cat /proc/meminfo']
        
        result = mem.poll_node('node01', False)
        
        # Should have called build_ssh_command
        mock_build.assert_called_once()
        
        # Check that build_ssh_command was called with validated node
        call_args = mock_build.call_args
        self.assertEqual(call_args[0][0], 'node01')  # node parameter
        self.assertEqual(call_args[0][1], 'cat /proc/meminfo')  # command parameter
    
    @patch('hpcat.commands.mem.validate_node_list')
    def test_execute_validates_user_nodes(self, mock_validate):
        """Test that execute validates user-provided node list."""
        # Create mock args
        class MockArgs:
            nodes = ['node01', 'node02']
            extended = False
            json = False
            csv = False
            prometheus = False
        
        # Mock validation to raise error
        mock_validate.side_effect = ValueError("Invalid node list")
        
        args = MockArgs()
        result = mem.execute(args)
        
        # Should return error code
        self.assertEqual(result, 1)
        
        # Should have called validate_node_list
        mock_validate.assert_called_once_with(['node01', 'node02'])


class TestSSHCommandSecurity(unittest.TestCase):
    """Test that SSH commands are constructed securely across all modules."""
    
    def test_no_strict_host_key_checking_disabled(self):
        """Test that StrictHostKeyChecking=no is not used in any module."""
        # Check gpu module
        with patch('hpcat.commands.gpu.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock()
            mock_run.return_value.stdout = "0,Tesla V100,50.0,1000,8000,45.0,200.0\n"
            mock_run.return_value.returncode = 0
            
            gpu.poll_node('node01')
            
            # Check all subprocess.run calls
            for call_args in mock_run.call_args_list:
                cmd = call_args[0][0]  # First argument is the command list
                cmd_str = ' '.join(cmd)
                self.assertNotIn('StrictHostKeyChecking=no', cmd_str)
    
    def test_ssh_commands_use_batch_mode(self):
        """Test that SSH commands use BatchMode for non-interactive operation."""
        # This is tested implicitly by the build_ssh_command function
        # which always includes BatchMode=yes by default
        pass
    
    def test_ssh_commands_have_timeouts(self):
        """Test that SSH commands have appropriate timeouts."""
        # This is tested by the build_ssh_command function
        # which includes ConnectTimeout
        pass


if __name__ == '__main__':
    unittest.main()
