import os

# Set testing environment variables before any app modules are imported
os.environ["TESTING"] = "1"
os.environ["DEV_MODE"] = "1"
