import subprocess
from pathlib import Path

from ruamel.yaml import YAML

SCRIPT_DIR = Path(__file__).resolve().parent

env = {
    "LLDAP_HTTPURL": "http://0.0.0.0:17170",
    "LLDAP_USERNAME": "admin",
    "LLDAP_PASSWORD": "password",
}


def create_group(group: str):
    cmd = f"{SCRIPT_DIR}/lldap.sh group add {group}"
    subprocess.run(cmd.split(), env=env)


def create_user(uid, email, display_name, first_name, last_name):
    cmd = f"{SCRIPT_DIR}/lldap.sh user add {uid} {email} -d {display_name} -f {first_name} -l {last_name}"
    subprocess.run(
        cmd.split(),
        env=env,
    )


def add_user_to_group(uid, group):
    cmd = f"{SCRIPT_DIR}/lldap.sh user group add {uid} {group}"
    subprocess.run(
        cmd.split(),
        env=env,
    )

def set_user_password(uid, password):
    cmd = f"docker exec -t lldap /app/lldap_set_password --username {uid} --password {password} --admin-username {env['LLDAP_USERNAME']} --admin-password {env['LLDAP_PASSWORD']} --base-url {env['LLDAP_HTTPURL']}"
    subprocess.run(
        cmd.split(),
        env=env,
    )


if __name__ == "__main__":

    with open(SCRIPT_DIR / "test.yml") as f:
        yaml = YAML().load(f)
        groups = yaml["groups"]
        users = yaml["users"]

    for g in groups:
        create_group(g)

    for u in users:
        uid = u["uid"]
        email = u["email"]
        password = u["password"]
        display_name = u["display_name"]
        first_name = u["first_name"]
        last_name = u["last_name"]
        groups = u["groups"]

        create_user(uid, email, display_name, first_name, last_name)
        set_user_password(uid, password)

        for g in groups:
            add_user_to_group(uid, g)
