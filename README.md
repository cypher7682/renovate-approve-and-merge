# PR Approve and Merge
This GitHub action essentially looks for PRs in a given organisation that have a given
label. Said label indicates to the action that the PR is to be approved and merged.

## Best case scenario / Caveats
Change makers can't approve their own code, so run your renovate changes as Linus 
Torvalds or something, and use a separate GitHub token for the PR raising/approving/merging.

Ideally you'd want to run the renovate job where it says `<RENOVATE_HERE>` in the example 
below - that way, the PRs renovate raises will be automagically merged when the job 
moves onto the automerge phase.

## Example Inputs:
```
jobs:
  renovate:
    runs-on: ubuntu-latest
    steps:
# <RENOVATE_HERE>
      - name: Automerge
        uses: cypher7682/renovate-approve-and-merge@v1.0.0
        with:
          github_token: ${{ secrets.RENOVATE_TOKEN }}
          organisation: <organisation>
          repo_filter: terraform
          label: rnvt-automerge
          no_label: rnvt-no-merge
          merge: 1
          debug: 0
```

