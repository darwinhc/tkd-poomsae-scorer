import os

# Tests configure their own settings; they must not depend on a local .env file.
os.environ.setdefault("TKD_REQUIRE_ENV_FILE", "false")
