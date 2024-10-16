# File: main.py
import os
import random
import json
import requests
from app_base import ApplicationBase, create_directory, create_file, check_file_exists
from loguru import logger
from collections import OrderedDict
from pathlib import Path

logger.add("app.log", level="DEBUG")  # Logs to a file with debug level

STATISTICAL_SECURITY = 2**30
RING_DATA_FILE = "https://raw.githubusercontent.com/snwagh/private-histogram/data/data.json"

def prg(seed, key_name):
    """A basic deterministic PRG."""
    random.seed(f"{seed}_{key_name}")
    return random.randint(1, STATISTICAL_SECURITY)

class PrivateHistogram(ApplicationBase):
    """The private histogram app, requiring at least 3 users for operation. The following directory structure 
    will be created by this app. app_pipelines/private-histogram/ will contain app generated data and 
    private/private-histogram/ will contain user generated data (start by adding a file named 'my_data.json' 
    in this directory and creating the permsfile). The global config (such as members etc.) is stored in 
    the RING_DATA_FILE.

    Directory structure:
    ├── sync/
    │   ├── <user_id>
    │   │   ├── app_pipelines/
    │   │   │   └── private-histogram/  
    │   │   ├── private/
    │   │   │   ├── _.syftperm
    │   │   │   └── private-histogram/
    │   │   └── public/           # Public directory for shared resources
    │   │       └── _.syftperm     # Permissions file for public folder access
    
    """

    def __init__(self):
        self.app_name = "private-histogram"
        super().__init__(os.environ.get("SYFTBOX_CLIENT_CONFIG_PATH"))
        self.my_user_id = self.client_config["email"]
        self.prev_user_id, self.next_user_id = self.get_neighbors()

    def get_neighbors(self):
        """Determine previous and next neighbors in the ring based on the data file."""
        data = json.loads(requests.get(RING_DATA_FILE).text)
        ring_participants = data["ring"]

        try:
            index = ring_participants.index(self.my_user_id)
        except ValueError:
            raise ValueError(f"user_id {self.my_user_id} not found in the ring.")

        prev_index = (index - 1) % len(ring_participants)
        next_index = (index + 1) % len(ring_participants)
        logger.info(
            f"Neighbors determined: previous={ring_participants[prev_index]}, next={ring_participants[next_index]}"
        )
        return ring_participants[prev_index], ring_participants[next_index]

    def setup_folder_perms(self):
        """Configure specific permissions for the first and second folders."""
        next_dir_path = self.app_dir(self.next_user_id) / "first"
        self.set_permissions(next_dir_path, [self.next_user_id], [self.my_user_id])

        my_dir_path = self.app_dir(self.my_user_id) / "second"
        self.set_permissions(my_dir_path, [self.my_user_id], [self.my_user_id])

        logger.info("Folder permissions set up.")

    def get_key_paths(self, user_id, key_number):
        """Get the path to the key file for the specified user and key number."""
        return self.app_dir(user_id) / key_number / "key.txt"

    def create_secret_value(self):
        """Generate a random secret value and write it to the second folder."""
        key_file_path = self.get_key_paths(self.my_user_id, "second")
        secret_value = random.randint(1, STATISTICAL_SECURITY)
        create_file(key_file_path, str(secret_value))
        logger.info(f"Created secret value in {key_file_path}")
        return secret_value

    def write_to_next_person(self, secret_value):
        """Write the secret value to the 'first' folder of the next person in the ring."""
        output_path = self.get_key_paths(self.next_user_id, "first")
        create_file(output_path, str(secret_value))
        logger.info(f"Sent secret value to {output_path}")

    def generate_my_data(self):
        """Creates a 'my_data.json' file with random values in the user's private directory."""
        data_template = {
            "view_time": lambda: random.randint(10, 20),
            "average_views_per_day": lambda: random.randint(1, 5),
            "num_movies_watched": lambda: random.randint(5, 10),
            "num_movies_rated": lambda: random.randint(0, 5),
        }

        my_data = {key: generator() for key, generator in data_template.items()}
        
        my_data_path = self.private_dir(self.my_user_id) / "my_data.json"
        create_directory(my_data_path.parent)  # Ensure directory exists
        self.set_permissions(my_data_path.parent, [self.my_user_id], [self.my_user_id])
        create_file(my_data_path, json.dumps(my_data))
        
        logger.info(f"Generated 'my_data.json' at {my_data_path} with random values.")

    def load_my_data(self):
        """Load user's data from 'my_data.json' and return it in a fixed order."""
        my_data_path = self.private_dir(self.my_user_id) / "my_data.json"
        if not check_file_exists(my_data_path):
            logger.info(f"File {my_data_path} does not exist.")
            
        with open(my_data_path) as f:
            data = json.load(f)
        return OrderedDict(sorted(data.items()))  # Ensure a consistent ordering for processing

    def encrypt_data(self, my_data, first_key, second_key):
        """Encrypt each field in my_data with a unique prg_diff for each field."""
        encrypted_data = {}
        for key, value in my_data.items():
            prg_diff = prg(first_key, key) - prg(second_key, key)
            encrypted_data[key] = str(int(value) + prg_diff)
        return encrypted_data

    def create_encrypted_data_file(self):
        """Stage 2: Read 'my_data.json' and create 'encrypted_data.json'."""
        logger.info("Attempting encryption of data")
        my_data = self.load_my_data()

        # Generate PRG differences based on keys
        first_key = int(open(self.get_key_paths(self.my_user_id, "first")).read())
        second_key = int(open(self.get_key_paths(self.my_user_id, "second")).read())

        # Encrypt data and save it
        encrypted_data = self.encrypt_data(my_data, first_key, second_key)
        encrypted_data_path = self.public_dir(self.my_user_id) / self.app_name / "encrypted_data.json"
        create_directory(encrypted_data_path.parent)
        create_file(encrypted_data_path, json.dumps(encrypted_data))
        logger.info(f"Encrypted data saved to {encrypted_data_path}")

    def aggregate_data(self):
        """Stage 3: Aggregate data from all ring members' encrypted files and calculate the average."""
        data = json.loads(requests.get(RING_DATA_FILE).text)
        ring_participants = data["ring"]
        num_members = len(ring_participants)

        # Initialize aggregate structure
        aggregate = {
            "view_time": 0,
            "average_views_per_day": 0,
            "num_movies_watched": 0,
            "num_movies_rated": 0,
        }

        # Sum up values from all participants' encrypted data files
        for user_id in ring_participants:
            encrypted_file = self.public_dir(user_id) / self.app_name / "encrypted_data.json"
            if check_file_exists(encrypted_file):
                with open(encrypted_file) as f:
                    user_data = json.load(f)
                    for key, value in user_data.items():
                        aggregate[key] += int(value)
            else:
                logger.info(f"Waiting for {encrypted_file} to be available.")
                return False  # Wait for all users to have the file

        # Calculate average for each key by dividing by the number of ring members
        average_data = {key: total / num_members for key, total in aggregate.items()}

        # Save aggregate (average) data
        aggregate_data_path = self.private_dir(self.my_user_id) / self.app_name / "aggregate_data.json"
        create_directory(aggregate_data_path.parent)
        create_file(aggregate_data_path, json.dumps(average_data))
        logger.info(f"Aggregate (average) data saved to {aggregate_data_path}")

        return True

if __name__ == "__main__":
    logger.info("-----------------------------")
    runner = PrivateHistogram()
    
    # Check if 'aggregate_data.json' already exists; if so, exit
    aggregate_data_path = runner.private_dir(runner.my_user_id) / runner.app_name / "aggregate_data.json"
    if check_file_exists(aggregate_data_path):
        logger.info("Aggregate data already exists. Exiting application.")
        exit()

    # Generate 'my_data.json' with random values (only if it doesn’t already exist)
    my_data_path = runner.private_dir(runner.my_user_id) / "my_data.json"
    if not check_file_exists(my_data_path):
        runner.generate_my_data()

    # Stage 1: Key Setup
    if not check_file_exists(runner.get_key_paths(runner.my_user_id, "second")) or \
       not check_file_exists(runner.get_key_paths(runner.my_user_id, "first")):
        runner.setup_folder_perms()
        logger.info("Setup complete.")

        if not check_file_exists(runner.get_key_paths(runner.my_user_id, "second")):
            logger.info("Second key does not exist. Creating a new one.")
            secret_value = runner.create_secret_value()
            runner.write_to_next_person(secret_value)

        if check_file_exists(runner.get_key_paths(runner.my_user_id, "first")):
            logger.info("Key exchange complete.")
        else:
            logger.info("Key exchange incomplete.")
    else:
        logger.info("Key setup already complete.")

    # Stage 2: Encrypt Data (only if 'encrypted_data.json' doesn’t already exist)
    encrypted_data_path = runner.public_dir(runner.my_user_id) / runner.app_name / "encrypted_data.json"
    if not check_file_exists(encrypted_data_path):
        if check_file_exists(runner.get_key_paths(runner.my_user_id, "second")) and \
           check_file_exists(runner.get_key_paths(runner.my_user_id, "first")):
            runner.create_encrypted_data_file()
        else:
            logger.info("Encryption stage incomplete, waiting for keys.")
    else:
        logger.info("Encrypted data already exists.")

    # Stage 3: Aggregate Data (only proceed if not already aggregated)
    if not check_file_exists(aggregate_data_path):
        if runner.aggregate_data():
            logger.info("Data aggregation complete.")
        else:
            logger.info("Waiting for all participants to complete encryption.")
    else:
        logger.info("Aggregate data already exists, no further action needed.")
    
    logger.info("-----------------------------")