import logging
import re
import sys
import time
from actions_toolkit import core, github

import github.GithubException
from github import Github

# make it possible to run these locally
# Github token should be passed through as an arg.

GIT_TOKEN = core.get_input("github_token") or sys.argv[1]
ORG = core.get_input("organisation") or sys.argv[2]
REPO_FILTER = core.get_input("repo_filter") or sys.argv[3]
LABEL = core.get_input("label") or sys.argv[4]
NO_LABEL = core.get_input("no_label") or sys.argv[5]
MERGE = core.get_input("merge") or sys.argv[6]
DEBUG = core.get_input("debug") or sys.argv[7]
MERGE = MERGE in ["True", "true", "1", "yes", "Yes"]
DEBUG = DEBUG in ["True", "true", "1", "yes", "Yes"]

logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO, format='[%(levelname)s][%(name)s] %(message)s')
logging.getLogger('github.Requester').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

def get_org_repos(user, org):
    for repo in user.get_user().get_repos():
        repo.log = logging.getLogger("REPO")

        if repo.organization.login != org:
            repo.log.debug(f"Skipping {repo.name} because it's not in {org}")
            continue
        try:
            if re.search(REPO_FILTER, repo.name):
                yield repo
            else:
                repo.log.debug(f"'{repo.name}' was filtered out because it didn't match '{REPO_FILTER}'")
        except github.GithubException as e:
            org.log.error("This token has not been given permissions to access these repos")


def put_pull_attrs(pull):
    pull.log = logging.getLogger("PULL")
    pull.real_url = pull.url.replace('api.', '').replace('repos/', '').replace('pulls', 'pull')


def refresh_pull(repo, pull):
    p = repo.get_pull(pull.number)
    put_pull_attrs(p)
    return p


def get_repo_pulls(repo):
    for pull in repo.get_pulls(state="open"):
        put_pull_attrs(pull)
        if NO_LABEL in [l.name for l in pull.labels]:
            pull.log.debug(f"{pull.real_url} has '{NO_LABEL}' - ignoring")
        elif LABEL in [l.name for l in pull.labels]:
            pull.log.debug(f"{pull.real_url} has '{LABEL}' and no '{NO_LABEL}' - doing")
            yield pull
        else:
            pull.log.debug(f"{pull.real_url} was filtered out because labels didn't match")


def review_pull(pull):
    pull.log.debug(f"Posting approval review to {pull.real_url}")
    pull.create_review(event="APPROVE")
    pull.log.info(f"Approval posted to {pull.real_url}")
    return True


def merge_pull(pull):
    pull.log.debug(f"Merging {pull.url}")
    methods = ["squash", "rebase", "merge"]
    for method in methods:
        try:
            pull.merge(merge_method=method)
            pull.log.info(f"Merged {pull.real_url}")
            return True
        except github.Github as e:
            continue
    else:
        pull.log.error(f"Could not merge {pull.real_url}")
        return False

def is_mergable(pull):
    return pull.mergeable_state == "clean" and pull.mergeable

def is_dirty(pull):
    return pull.mergeable_state == "dirty"

def comment(pull, m):
    pull.create_comment(m)
    return True

if __name__ == '__main__':
    log = logging.getLogger("MAIN")
    g = Github(GIT_TOKEN)

    for repo in get_org_repos(g, ORG):
        if repo.organization.login != ORG:
            continue
        else:
            log.debug(f"Fetching pulls for '{repo.name}'")

            for pull in get_repo_pulls(repo):
                log.info(f"{pull.real_url} Found")
                log.info(f"{pull.real_url} - Mergability State: {pull.mergeable_state}, {pull.mergeable}")

                if not is_mergable(pull):
                    if is_dirty(pull):
                        pull.log.info(f"{pull.real_url} - Dirty.")
                        comment(pull, "This PR is not mergeable. Please rebase and try again.")
                        continue
                    pull.log.info(f"{pull.real_url} - Not mergeable. Posting approval.")
                    review_pull(pull)
                    refresh_pull(repo, pull)

                i = 0

                while i<10:

                    # refresh the object, as the mergability doesn't seem to update
                    pull.log.debug(f"{pull.real_url} - refreshing pull object")
                    pull = refresh_pull(repo, pull)

                    if is_mergable(pull):
                        pull.log.info(f"{pull.real_url} - Mergable")
                        merge_pull(pull)
                        break

                    if i:
                        pull.log.warning(f"{pull.real_url} - Back-off {i+1}s waiting for mergability")

                    i += 1
                    time.sleep(i)
                else:
                    pull.log.error(f"{pull.real_url} - Could not merge after 10 attempts")
