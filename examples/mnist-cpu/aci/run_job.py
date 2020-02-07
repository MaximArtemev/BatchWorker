import os
import sh
import uuid
import yaml
import logging
import datetime
import argparse
import datetime
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def check_file(path):
    if os.path.isfile(path):
        return True
    else:
        logging.exception(f" No file {path} ")
        raise


def proc_config(config: Path):
    _config = config.parent / f"_{config.name}"
    sh.envsubst(sh.cat(str(config)), _out=str(_config))
    with open(str(_config), 'r') as f:
        _config_spec = yaml.load(f.read())
    return _config, _config_spec


def gen_tag(user):
    time = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    return f"{user}-{time}-{str(uuid.uuid4())[:2]}"


def console_command(cmd: list, timeout=10000, *args, **kwargs):
    process = subprocess.Popen(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               universal_newlines=True, *args, **kwargs)

    start = datetime.datetime.now()
    while (datetime.datetime.now() - start).seconds < timeout:
        output = process.stdout.readline()
        print(output.strip())
        return_code = process.poll()
        if return_code is not None:
            print('RETURN CODE', return_code)
            # Process has finished, read rest of the output
            for output in process.stdout.readlines():
                print(output.strip())
            break


def aci_run(notebook: Path, config: Path):
    try:
        console_command(["az", "account", "show"])
    except Exception as exp:
        logging.error(
            f"Launch /etc/azcreds/azlogin.sh or login to your Azure account `az login`")
        console_command(["/bin/bash", "-c", "/etc/azcreds/azlogin.sh"])

    console_command(["jupyter", "nbconvert", "--to script", str(notebook)])
    script = notebook.parent / notebook.name.replace("ipynb", "py")

    USER_CLUSTER_NAME = os.environ["USER_CLUSTER_NAME"]
    ACI_PERS_RESOURCE_GROUP = os.environ["ACI_PERS_RESOURCE_GROUP"]
    ACI_PERS_STORAGE_ACCOUNT_NAME = os.environ["ACI_PERS_STORAGE_ACCOUNT_NAME"]
    ACI_PERS_SHARE_NAME = os.environ["ACI_PERS_SHARE_NAME"]
    SAS_TOKEN = os.environ["SAS_TOKEN"]
    EXPERIMENT_FOLDER = gen_tag(USER_CLUSTER_NAME)
    os.environ["EXPERIMENT_FOLDER"] = EXPERIMENT_FOLDER
    os.environ["RESOURCE_NAME"] = EXPERIMENT_FOLDER

    _config, _config_spec = proc_config(config)
    group_name = f"{_config_spec['name']}"

    STORAGE_URI = "https://{}.file.core.windows.net/{}/{}/{}?{}".format(
        ACI_PERS_STORAGE_ACCOUNT_NAME,
        ACI_PERS_SHARE_NAME,
        EXPERIMENT_FOLDER,
        "{}",
        SAS_TOKEN)

    console_command(["azcopy", "cp", str(_config), STORAGE_URI.format(_config.name)])
    console_command(["azcopy", "cp", str(script), STORAGE_URI.format(script.name)])

    console_command(
        ["az", "container", "create", "-g", ACI_PERS_RESOURCE_GROUP, "--file",
         str(_config)])
    console_command(
        ["az", "container", "logs", "--follow", "-g", ACI_PERS_RESOURCE_GROUP, "-n",
         group_name])

    console_command(["azcopy", "cp",
                     STORAGE_URI.format('*'), f"./{EXPERIMENT_FOLDER}",
                     "--recursive=true"])
    console_command(
        ["az", "container", "delete", "-g", ACI_PERS_RESOURCE_GROUP, "-n",
         group_name, "-y"])

    return 0


def main():
    parser = argparse.ArgumentParser(description="Run job on the ACI")
    parser.add_argument('--notebook', help='Specify jupyter notebook file',
                        required=True)
    parser.add_argument('--config', help='Specify config file', required=True)
    parser.add_argument('--cluster', help='Choose cluster', default="ACI")
    args = parser.parse_args()

    check_file(args.notebook)
    check_file(args.config)
    notebook = Path(args.notebook)
    os.environ["PYSCRIPT"] = notebook.name.replace(".ipynb", "")

    if args.cluster == "ACI":
        aci_run(notebook, Path(args.config))
    else:
        logging.error(f"Method {args.cluster} is not realised :(")
        return 2


if __name__ == '__main__':
    main()
