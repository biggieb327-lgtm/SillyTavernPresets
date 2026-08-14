Deploy one or all bot instances to the VPS.

Load the `deploy-and-verify-fleet` skill and follow its procedure. The
instance name is the first argument; omit it to deploy all seven.

Before deploying: verify the branch is green (`bash .claude/tools/verify.sh`)
and merged to `main`. A red eval suite on `main` is a deploy blocker.
