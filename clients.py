#!/usr/bin/env python3
"""
Remote Command System - Client Side
Polls the server for commands and executes them

Usage:
    python client.py --server http://server:5000 [--name CLIENT_NAME] [--interval 30]
"""
import os
import sys
import json
import time
import uuid
import platform
import subprocess
import tempfile
import zipfile
import socket
import logging
from pathlib import Path
import requests
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('client.log')
    ]
)
logger = logging.getLogger(__name__)

class RemoteCommandClient:
    def __init__(self, server_url, client_name=None, poll_interval=30):
        """
        Initialize the remote command client
        
        Args:
            server_url (str): URL of the command server
            client_name (str, optional): Name for this client. Defaults to hostname.
            poll_interval (int, optional): How often to poll for commands in seconds. Defaults to 30.
        """
        self.server_url = server_url.rstrip('/')
        self.client_name = client_name or socket.gethostname()
        self.poll_interval = poll_interval
        self.client_id = None
        self.client_id_file = Path("client_id.txt")
        
        # Gather system information
        self.os_info = platform.system()
        self.version_info = platform.version()
        
        # Load client ID if it exists
        self._load_client_id()
        
    def _load_client_id(self):
        """Load the client ID from disk if it exists"""
        if self.client_id_file.exists():
            try:
                self.client_id = self.client_id_file.read_text().strip()
                logger.info(f"Loaded existing client ID: {self.client_id}")
            except Exception as e:
                logger.error(f"Failed to load client ID: {e}")
                
    def _save_client_id(self):
        """Save the client ID to disk"""
        try:
            self.client_id_file.write_text(self.client_id)
            logger.info(f"Saved client ID: {self.client_id}")
        except Exception as e:
            logger.error(f"Failed to save client ID: {e}")
            
    def register(self):
        """Register with the server and get a client ID"""
        if self.client_id:
            logger.info("Already registered with ID: " + self.client_id)
            return True
            
        try:
            url = urljoin(self.server_url, "/get-id")
            data = {
                "name": self.client_name,
                "os": self.os_info,
                "version": self.version_info
            }
            
            logger.info(f"Registering client with server: {data}")
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                self.client_id = response.json()["client_id"]
                self._save_client_id()
                logger.info(f"Successfully registered with ID: {self.client_id}")
                return True
            else:
                logger.error(f"Failed to register: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
            
    def get_actions(self):
        """Get actions from the server"""
        if not self.client_id:
            logger.error("No client ID available. Register first.")
            return []
            
        try:
            url = urljoin(self.server_url, f"/get-actions/{self.client_id}")
            response = requests.get(url)
            
            if response.status_code == 200:
                actions = response.json().get("actions", [])
                if actions:
                    logger.info(f"Received {len(actions)} action(s) from server")
                return actions
            else:
                logger.error(f"Failed to get actions: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting actions: {e}")
            return []
    
    def execute_runpy(self, code):
        """Execute Python code inline"""
        try:
            # Create a temporary file to capture output
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.py', delete=False) as temp:
                temp_path = temp.name
                # Write a wrapper script that captures stdout/stderr
                temp.write(f"""
import sys
import io
from contextlib import redirect_stdout, redirect_stderr

captured_output = io.StringIO()
try:
    with redirect_stdout(captured_output), redirect_stderr(captured_output):
        # User code starts here
{code}
        # User code ends here
    exit_code = 0
except Exception as e:
    captured_output.write(f"Error: {{e}}")
    exit_code = 1

# Write output to file
with open("{temp_path}.out", "w") as f:
    f.write(captured_output.getvalue())
sys.exit(exit_code)
""")
                
            # Execute the temporary script
            subprocess.run([sys.executable, temp_path], check=False)
            
            # Read the captured output
            with open(f"{temp_path}.out", "r") as f:
                output = f.read()
                
            # Clean up temporary files
            os.unlink(temp_path)
            os.unlink(f"{temp_path}.out")
            
            return output
            
        except Exception as e:
            return f"Failed to execute Python code: {e}"
    
    def execute_run_file(self, filename):
        """Execute a Python file"""
        try:
            # Create file path
            file_path = Path(filename)
            
            if not file_path.exists():
                return f"Error: File '{filename}' not found"
                
            # Execute the script and capture output
            result = subprocess.run(
                [sys.executable, file_path], 
                capture_output=True,
                text=True
            )
            
            # Combine stdout and stderr
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
                
            return output
            
        except Exception as e:
            return f"Failed to execute Python file: {e}"
    
    def execute_command(self, command):
        """Execute a shell command"""
        try:
            # Execute the command and capture output
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True,
                text=True
            )
            
            # Combine stdout and stderr
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
                
            return output
            
        except Exception as e:
            return f"Failed to execute command: {e}"
    
    def download_and_extract_zip(self, url):
        """Download a ZIP file and extract it to the current directory"""
        try:
            # Download the file
            logger.info(f"Downloading ZIP file from: {url}")
            response = requests.get(url, stream=True)
            
            if response.status_code != 200:
                return f"Failed to download ZIP: {response.status_code} - {response.text}"
                
            # Save the ZIP file to a temporary location
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp:
                temp_path = temp.name
                for chunk in response.iter_content(chunk_size=8192):
                    temp.write(chunk)
                    
            # Extract the ZIP file
            logger.info(f"Extracting ZIP file to current directory")
            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                zip_ref.extractall('.')
                
            # Clean up the temporary ZIP file
            os.unlink(temp_path)
            
            return f"Successfully downloaded and extracted ZIP from {url}"
            
        except Exception as e:
            return f"Failed to download or extract ZIP: {e}"
    
    def execute_action(self, action):
        """Execute a single action based on its type"""
        action_type = action.get("type")
        action_data = action.get("data")
        
        logger.info(f"Executing action: {action_type}")
        
        if action_type == "runpy":
            output = self.execute_runpy(action_data)
        elif action_type == "run":
            output = self.execute_run_file(action_data)
        elif action_type == "cmd":
            output = self.execute_command(action_data)
        elif action_type == "zipfile":
            output = self.download_and_extract_zip(action_data)
        else:
            output = f"Unknown action type: {action_type}"
            
        return {
            "action": action,
            "output": output
        }
    
    def report_results(self, results):
        """Report action results back to the server"""
        if not results:
            return True
            
        try:
            url = urljoin(self.server_url, "/report-results")
            data = {
                "client_id": self.client_id,
                "results": results
            }
            
            logger.info(f"Reporting {len(results)} result(s) to server")
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                logger.info("Successfully reported results")
                return True
            else:
                logger.error(f"Failed to report results: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error reporting results: {e}")
            return False
    
    def run_once(self):
        """Run a single polling cycle"""
        if not self.client_id and not self.register():
            logger.error("Failed to register with server")
            return False
            
        # Get actions from server
        actions = self.get_actions()
        
        if not actions:
            return True
            
        # Execute actions and collect results
        results = []
        for action in actions:
            result = self.execute_action(action)
            results.append(result)
            
        # Report results back to server
        return self.report_results(results)
    
    def run_forever(self):
        """Run the polling loop forever"""
        logger.info(f"Starting client polling loop every {self.poll_interval} seconds")
        
        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in polling cycle: {e}")
                
            time.sleep(self.poll_interval)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Remote Command Client")
    parser.add_argument("--server", required=True, help="Server URL (e.g., http://example.com:5000)")
    parser.add_argument("--name", help="Client name (defaults to hostname)")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds")
    
    args = parser.parse_args()
    
    client = RemoteCommandClient(
        server_url=args.server,
        client_name=args.name,
        poll_interval=args.interval
    )
    
    try:
        client.run_forever()
    except KeyboardInterrupt:
        logger.info("Client terminated by user")