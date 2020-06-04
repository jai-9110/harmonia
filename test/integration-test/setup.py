import os
import sys
import subprocess
import json
import time
import logging
import tempfile
import requests
from requests.auth import HTTPBasicAuth

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN = 'harmonia_admin'
PASSWORD = 'password'
BASIC_AUTH = HTTPBasicAuth(ADMIN, PASSWORD)
GITEA_URI = 'test_gitea:3000'

subprocess.run(["git", "config", "--global", "user.email", "admin@admin.com"])
subprocess.run(["git", "config", "--global", "user.name", ADMIN])


def create_repo(repo_name):
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
    }

    def is_repo_existed():
        response = requests.get(
            'http://{}/api/v1/repos/{}/{}'.format(GITEA_URI, ADMIN, repo_name), headers=headers, auth=HTTPBasicAuth(ADMIN, PASSWORD))
        return response.status_code == 200

    if not is_repo_existed():
        logger.info("Creating {} repository...".format(repo_name))

        # data = '{ "name": "{}" }'.format(repo_name)
        data = json.dumps({'name': repo_name})

        response = requests.post(
            'http://{}/api/v1/user/repos'.format(GITEA_URI), headers=headers, data=data, auth=HTTPBasicAuth(ADMIN, PASSWORD))

        if response.status_code == 422:
            logger.info("response: {}".format(response.text))
            raise Exception('APIValidationError: error format response related to input validation')

    else:
        logger.info(
            "Repository {} already exists, skipping creating.".format(repo_name))


def create_webhook(repo_name, target_url):
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
    }

    def is_webhook_exists():
        response = requests.get(
            'http://{}/api/v1/repos/{}/{}/hooks'.format(GITEA_URI, ADMIN, repo_name), headers=headers, auth=BASIC_AUTH)
        webhooks = response.json()
        return any(w.get('config').get('url') == target_url for w in webhooks)

    if not is_webhook_exists():
        logger.info('creating a webhook from repo {} to {}...'.format(
            repo_name, target_url))

        data = json.dumps({
            'active': True,
            'config': {
                'content_type': 'json',
                'url': target_url
            },
            'events': ['push'],
            'type': 'gitea'
        })
        # data = '{ "active": true, "config": { "content_type": "json", "url": "{}" }, "events": [ "push" ], "type": "gitea"}'.format(target_url)
        response = requests.post(
            'http://{}/api/v1/repos/{}/{}/hooks'.format(GITEA_URI, ADMIN, repo_name), headers=headers, data=data, auth=BASIC_AUTH)
        if response.status_code != 201:
            logger.info("response: {}".format(response.text))
            raise Exception(
                'Create webhook fail.')
    else:
        logger.info('the webhook from repo {} to {} is already existed, skipping creating...'.format(
            repo_name, target_url))


def clone_repo(repo_name):
    logger.info("Cloning repository {}...".format(repo_name))
    cmd = ['git', 'clone', 'http://{}/{}/{}.git'.format(GITEA_URI, ADMIN, repo_name)]
    run_commands([cmd])


def is_gitea_ready():
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
    }
    try:
        response = requests.get(
            'http://{}/api/v1/user'.format(GITEA_URI), headers=headers, auth=BASIC_AUTH)
        if response.status_code == 200:
            return True
        logger.info("response: {}".format(response.text))
    except requests.exceptions.ConnectionError:
        logger.info("connection timeout, reconnect...")
    return False

def init_gitea():
    while not is_gitea_ready():
        logger.info("sleep to wait gitea ready")
        time.sleep(30)

    create_repo('global-model')
    create_repo('local-model1')
    create_repo('train-plan')

    create_webhook(
        'global-model', 'http://integration-test_edge-operator_1:8090/')
    create_webhook(
        'local-model1', 'http://integration-test_aggregator-operator_1:9080/')
    create_webhook(
        'train-plan', 'http://integration-test_edge-operator_1:8090/')
    create_webhook(
        'train-plan', 'http://integration-test_aggregator-operator_1:9080/')


def run_commands(cmds, cwd=None):
    for cmd in cmds:
        p = subprocess.run(cmd, cwd=cwd)
        if p.stdout:
            logger.info(p.stdout)
        if p.stderr:
            logger.info(p.stderr)


def setup_train_plan(plan):
    repo_name = 'train-plan'
    if not os.path.isdir(repo_name):
        clone_repo(repo_name)
    with open(os.path.join(repo_name, 'plan.json'), 'w') as file:
        json.dump(plan, file)
    run_commands([
        ['git', 'add', 'plan.json'],
        ['git', 'commit', '-m', 'update plan'],
        ['git', 'remote', 'rm', 'origin'],
        ['git', 'remote', 'add', 'origin', 'http://{}:{}@{}/{}/{}.git'.format(
            ADMIN, PASSWORD, GITEA_URI, ADMIN, repo_name)],
        ['git', 'push', '-u', 'origin', 'master']], cwd=repo_name)


if __name__ == "__main__":
    option = sys.argv[1]
    if option == 'init':
        init_gitea()
    elif option == 'set-plan':
        arg = sys.argv[2]
        print(arg)
        if arg:
            try:
                plan = json.loads(arg)
                setup_train_plan(plan)
            except json.JSONDecodeError as err:
                logger.error('json decode error {}'.format(err))
    else:
        logger.warning('unknown option: {}'.format(option))