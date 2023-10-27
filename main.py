import logging
import re
import sys
import time

import github.GithubException
from github import Github

# make it possible to run these locally
# Github token should be passed through as an arg.
try:
    sys.argv[2]
except IndexError:
    # we are running locally, so put some defaults in to make it easier to run it
    GIT_TOKEN = sys.argv[1]
    ORG = "sys.argv[2]"
    REPO_FILTER = "terraform"
    LABEL = "rnvt-automerge"
    NO_LABEL = "rnvt-no-merge"
    MERGE = True
    DEBUG = False
    INSTALLATION_ID = 32430040
else:
    # We're not running locally
    GIT_TOKEN = sys.argv[1]
    ORG = sys.argv[2]
    REPO_FILTER = sys.argv[3]
    LABEL = sys.argv[4]
    NO_LABEL = sys.argv[5]
    MERGE = sys.argv[6] == "True" or sys.argv[6] == "1"
    DEBUG = sys.argv[7] == "True" or sys.argv[7] == "1"
    INSTALLATION_ID = sys.argv[8]

logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO, format='[%(levelname)s][%(name)s] %(message)s')


def _get_orgs(g):
    org = g.get_organization(ORG)
    try:
        org.log = logging.getLogger("ORG")
        for installation in org.get_installations():
            if installation.id == int(INSTALLATION_ID):
                yield org
            else:
                org.log.debug(f"'{installation.id}' was filtered out because it didn't match '{INSTALLATION_ID}'")
    except github.GithubException:
        org.log.debug(f"No access to this org by SAML")


def _get_org_repos(org):
    for repo in org.get_repos():
        try:
            repo.log = logging.getLogger("REPO")
            if re.search(REPO_FILTER, repo.name):
                yield repo
            else:
                repo.log.debug(f"'{repo.name}' was filtered out because it didn't match '{REPO_FILTER}'")
        except github.GithubException as e:
            org.log.error("This token has not been given permissions to access these repos")


def _put_pull_attrs(pull):
    pull.log = logging.getLogger("PULL")
    pull.real_url = pull.url.replace('api.', '').replace('repos/', '').replace('pulls', 'pull')


def _refresh_pull(repo, pull):
    p = repo.get_pull(pull.number)
    _put_pull_attrs(p)
    return p


def _get_repo_pulls(repo):
    for pull in repo.get_pulls(state="open"):
        _put_pull_attrs(pull)
        if NO_LABEL in [l.name for l in pull.labels]:
            pull.log.debug(f"{pull.real_url} has '{NO_LABEL}' - ignoring")
        elif LABEL in [l.name for l in pull.labels]:
            pull.log.debug(f"{pull.real_url} has '{LABEL}' and no '{NO_LABEL}' - doing")
            yield pull
        else:
            pull.log.debug(f"{pull.real_url} was filtered out because labels didn't match")


def _review_pull(pull):
    pull.log.debug(f"Posting approval review to {pull.real_url}")
    pull.create_review(event="APPROVE")
    pull.log.info(f"Approval posted to {pull.real_url}")
    return True


def _merge_pull(pull):
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


if __name__ == '__main__':
    log = logging.getLogger("MAIN")
    g = Github(GIT_TOKEN)
    log.debug("Fetching orgs")

    for org in _get_orgs(g):
        org.log.debug(f"Fetching repos in '{org.name}'")

        for repo in _get_org_repos(org):
            repo.log.debug(f"Fetching pulls for '{repo.name}'")

            for pull in _get_repo_pulls(repo):
                pull.log.info(f"{pull.real_url} Found")

                if not pull.mergeable:
                    pull.log.info(f"{pull.real_url} is not mergable. Posting an approval to see if that fixes it.")
                    _review_pull(pull)

                i = 0
                while not pull.mergeable or pull.mergeable_state == "blocked":

                    # refresh the object, as the mergability doesn't seem to update
                    pull.log.debug(f"{pull.real_url} - refreshing pull object")
                    pull = _refresh_pull(repo, pull)

                    if not i:
                        pull.log.warning(f"{pull.real_url} - Approval did not make mergable.")
                    elif i < 10:
                        pull.log.warning(f"{pull.real_url} - Back-off {i+1}s waiting for mergability")
                    else:
                        pull.log.error(f"{pull.real_url} - Could not make mergeable. State: '{pull.mergeable_state}', Mergable: '{pull.mergeable}'")
                        issue = repo.get_issue(pull.number)
                        issue.create_comment(
                            f"Attempted to automerge this PR, but couldn't because it's in a merge state: \n `{pull.mergeable_state}`, and mergability: `{str(pull.mergeable)}`"
                        )
                        break
                    i += 1
                    time.sleep(i)

                else:
                    if MERGE:
                        pull.log.info(f"{pull.real_url} Mergeability State: {pull.mergeable_state}, {pull.mergeable}")
                        _merge_pull(pull)
